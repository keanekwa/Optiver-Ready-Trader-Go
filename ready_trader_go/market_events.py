# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import csv
import enum
import logging
import queue
import threading

from typing import Callable, Dict, List, Optional, TextIO

from .match_events import MatchEvents
from .order_book import IOrderListener, Order, OrderBook
from .types import Instrument, Lifespan, Side

MARKET_EVENT_QUEUE_SIZE = 1024
INPUT_SCALING = 100


class MarketEventOperation(enum.IntEnum):
    AMEND = 0
    CANCEL = 1
    INSERT = 2
    Amend = AMEND
    Cancel = CANCEL
    Insert = INSERT


class MarketEvent(object):
    """A market event."""
    __slots__ = ("time", "instrument", "operation", "order_id", "side", "volume", "price", "lifespan")

    def __init__(self, time: float, instrument: Instrument, operation: MarketEventOperation, order_id: int,
                 side: Optional[Side], volume: int, price: int, lifespan: Optional[Lifespan]):
        """Initialise a new instance of the MarketEvent class."""
        self.time: float = time
        self.instrument: Instrument = instrument
        self.operation: MarketEventOperation = operation
        self.order_id: int = order_id
        self.side: Optional[Side] = side
        self.volume: int = volume
        self.price: int = price
        self.lifespan: Optional[Lifespan] = lifespan


class MarketEventsReader(IOrderListener):
    """A processor of market events read from a file."""

    def __init__(self, filename: str, loop: asyncio.AbstractEventLoop, future_book: OrderBook, etf_book: OrderBook,
                 match_events: MatchEvents):
        """Initialise a new instance of the MarketEvents class.
        """
        self.etf_book: OrderBook = etf_book
        self.etf_orders: Dict[int, Order] = dict()
        self.event_loop: asyncio.AbstractEventLoop = loop
        self.filename: str = filename
        self.future_book: OrderBook = future_book
        self.future_orders: Dict[int, Order] = dict()
        self.logger: logging.Logger = logging.getLogger("MARKET_EVENTS")
        self.match_events: MatchEvents = match_events
        self.queue: queue.Queue = queue.Queue(MARKET_EVENT_QUEUE_SIZE)
        self.reader_task: Optional[threading.Thread] = None

        # Prime the event pump with a no-op event
        self.next_event: Optional[MarketEvent] = MarketEvent(0.0, Instrument.FUTURE, MarketEventOperation.CANCEL, 0,
                                                             Side.BUY, 0, 0, Lifespan.FILL_AND_KILL)

        # Allow other objects to get a callback when the reader task is complete
        self.task_complete: List[Callable] = list()

    # IOrderListener callbacks

    def on_order_amended(self, now: float, order: Order, volume_removed: int) -> None:
        """Called when the order is amended."""
        self.match_events.amend(now, "", order.client_order_id, -volume_removed)
        if order.remaining_volume == 0:
            if order.instrument == Instrument.FUTURE:
                del self.future_orders[order.client_order_id]
            elif order.instrument == Instrument.ETF:
                del self.etf_orders[order.client_order_id]

    def on_order_cancelled(self, now: float, order: Order, volume_removed: int) -> None:
        """Called when the order is cancelled."""
        self.match_events.cancel(now, "", order.client_order_id, -volume_removed)
        if order.instrument == Instrument.FUTURE and order.client_order_id in self.future_orders:
            del self.future_orders[order.client_order_id]
        elif order.instrument == Instrument.ETF and order.client_order_id in self.etf_orders:
            del self.etf_orders[order.client_order_id]

    def on_order_placed(self, now: float, order: Order) -> None:
        """Called when a good-for-day order is placed in the order book."""
        if order.instrument == Instrument.FUTURE:
            self.future_orders[order.client_order_id] = order
        elif order.instrument == Instrument.ETF:
            self.etf_orders[order.client_order_id] = order

    def on_order_filled(self, now: float, order: Order, price: int, volume: int, fee: int) -> None:
        """Called when the order is partially or completely filled."""
        if order.remaining_volume == 0:
            if order.instrument == Instrument.FUTURE and order.client_order_id in self.future_orders:
                del self.future_orders[order.client_order_id]
            elif order.instrument == Instrument.ETF and order.client_order_id in self.etf_orders:
                del self.etf_orders[order.client_order_id]

    def on_reader_done(self, num_events: int) -> None:
        """Called when the market data reader thread is done."""
        self.logger.info("reader thread complete after processing %d market events", num_events)

    def process_market_events(self, elapsed_time: float) -> None:
        """Process market events from the queue."""
        evt: MarketEvent = self.next_event

        while evt and evt.time < elapsed_time:
            if evt.instrument == Instrument.FUTURE:
                orders = self.future_orders
                book = self.future_book
            else:
                orders = self.etf_orders
                book = self.etf_book

            if evt.operation == MarketEventOperation.INSERT:
                order = Order(evt.order_id, evt.instrument, evt.lifespan, evt.side, evt.price, evt.volume, self)
                self.match_events.insert(evt.time, "", order.client_order_id, order.instrument, order.side,
                                         abs(order.volume), order.price, order.lifespan)
                book.insert(evt.time, order)
            elif evt.order_id in orders:
                order = orders[evt.order_id]
                if evt.operation == MarketEventOperation.CANCEL:
                    book.cancel(evt.time, order)
                elif evt.volume < 0:
                    # evt.operation must be MarketEventOperation.AMEND
                    book.amend(evt.time, order, order.volume + evt.volume)

            evt = self.queue.get()

        self.next_event = evt
        if evt is None:
            for c in self.task_complete:
                c(self)

    def reader(self, market_data: TextIO) -> None:
        """Read the market data file and place order events in the queue."""
        fifo = self.queue

        with market_data:
            csv_reader = csv.reader(market_data)
            next(csv_reader)  # Skip header row
            for row in csv_reader:
                # time, instrument, operation, order_id, side, volume, price, lifespan
                fifo.put(MarketEvent(float(row[0]), Instrument(int(row[1])), MarketEventOperation[row[2]],
                                     int(row[3]), Side[row[4]] if row[4] else None,
                                     int(float(row[5])) if row[5] else 0, int(float(row[6]) * INPUT_SCALING) if row[6] else 0,
                                     Lifespan[row[7]] if row[7] else None))
            fifo.put(None)

        self.event_loop.call_soon_threadsafe(self.on_reader_done, csv_reader.line_num - 1)

    def start(self):
        """Start the market events reader thread"""
        try:
            market_data = open(self.filename)
        except OSError as e:
            self.logger.error("failed to open market data file: filename='%s'" % self.filename, exc_info=e)
            raise
        else:
            self.reader_task = threading.Thread(target=self.reader, args=(market_data,), daemon=True, name="reader")
            self.reader_task.start()
