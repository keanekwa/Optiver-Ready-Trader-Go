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
import logging

from typing import Iterable, List, Optional, Tuple

from .messages import (HEADER, HEADER_SIZE, ORDER_BOOK_HEADER, ORDER_BOOK_HEADER_SIZE,
                       ORDER_BOOK_MESSAGE, ORDER_BOOK_MESSAGE_SIZE, TRADE_TICKS_HEADER, TRADE_TICKS_HEADER_SIZE,
                       TRADE_TICKS_MESSAGE, TRADE_TICKS_MESSAGE_SIZE, MessageType)
from .order_book import TOP_LEVEL_COUNT, OrderBook
from .pubsub import PublisherFactory
from .timer import Timer
from .types import Instrument


class InformationPublisher(asyncio.DatagramProtocol):
    """A publisher of exchange information."""

    def __init__(self, loop: asyncio.AbstractEventLoop, publisher_factory: PublisherFactory,
                 order_books: Iterable[OrderBook], timer: Timer):
        """Initialize a new instance of the InformationChannel class."""
        self.__event_loop: asyncio.AbstractEventLoop = loop
        self.__file_number: int = 0
        self.__logger: logging.Logger = logging.getLogger("INFORMATION")
        self.__order_books: Tuple[OrderBook] = tuple(order_books)
        self.__publisher_factory: PublisherFactory = publisher_factory
        self.__send_ticks_handles: List[Optional[asyncio.Handle]] = [None for _ in Instrument]
        self.__trade_ticks_sequences: List[int] = [1 for _ in Instrument]
        self.__transport: Optional[asyncio.WriteTransport] = None

        # Connect signals
        for book in self.__order_books:
            book.trade_occurred.append(self.on_trade)
        timer.timer_ticked.append(self.on_timer_tick)

        # Store book data for dissemination to competitors.
        self.__ask_prices: List[int] = [0] * TOP_LEVEL_COUNT
        self.__ask_volumes: List[int] = [0] * TOP_LEVEL_COUNT
        self.__bid_prices: List[int] = [0] * TOP_LEVEL_COUNT
        self.__bid_volumes: List[int] = [0] * TOP_LEVEL_COUNT

        # Message buffers
        self.__book_message = bytearray(ORDER_BOOK_MESSAGE_SIZE)
        self.__ticks_message = bytearray(TRADE_TICKS_MESSAGE_SIZE)
        HEADER.pack_into(self.__book_message, 0, ORDER_BOOK_MESSAGE_SIZE, MessageType.ORDER_BOOK_UPDATE)
        HEADER.pack_into(self.__ticks_message, 0, TRADE_TICKS_MESSAGE_SIZE, MessageType.TRADE_TICKS)

    def connection_made(self, transport: asyncio.WriteTransport) -> None:
        """Called when the datagram endpoint is created."""
        self.__logger.info("information channel established")
        self.__transport = transport

    def on_timer_tick(self, timer: Timer, now: float, tick_number: int) -> None:
        """Called each time the timer ticks."""
        for book in self.__order_books:
            book.top_levels(self.__ask_prices, self.__ask_volumes, self.__bid_prices, self.__bid_volumes)
            ORDER_BOOK_HEADER.pack_into(self.__book_message, HEADER_SIZE, book.instrument, tick_number)
            ORDER_BOOK_MESSAGE.pack_into(self.__book_message, ORDER_BOOK_HEADER_SIZE, *self.__ask_prices,
                                         *self.__ask_volumes, *self.__bid_prices, *self.__bid_volumes)
            self.__transport.write(self.__book_message)

    def on_trade(self, book: OrderBook) -> None:
        """Called when a trade occurs in one of the order books."""
        if self.__send_ticks_handles[book.instrument] is None:
            self.__send_ticks_handles[book.instrument] = self.__event_loop.call_soon(self.__send_trade_ticks, book)

    def __send_trade_ticks(self, order_book: OrderBook) -> None:
        """Prepare and send trade ticks for the given order book."""
        self.__send_ticks_handles[order_book.instrument] = None

        if order_book.trade_ticks(self.__ask_prices, self.__ask_volumes, self.__bid_prices, self.__bid_volumes):
            self.__trade_ticks_sequences[order_book.instrument] += 1
            TRADE_TICKS_HEADER.pack_into(self.__ticks_message, HEADER_SIZE, order_book.instrument,
                                         self.__trade_ticks_sequences[order_book.instrument])
            TRADE_TICKS_MESSAGE.pack_into(self.__ticks_message, TRADE_TICKS_HEADER_SIZE, *self.__ask_prices,
                                          *self.__ask_volumes, *self.__bid_prices, *self.__bid_volumes)
            self.__transport.write(self.__ticks_message)

    async def start(self) -> None:
        """Start this publisher."""
        typ = self.__publisher_factory.typ
        name = self.__publisher_factory.name
        self.__logger.info("starting information publisher: type=%s name=%s", typ, name)
        self.__publisher_factory.create(self)
