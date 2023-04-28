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
import collections
import csv
import itertools

from typing import Callable, Dict, Iterator, List, NamedTuple, Optional, Set, TextIO, Tuple

from PySide6 import QtCore,  QtNetwork

from ready_trader_go.account import AccountFactory, CompetitorAccount
from ready_trader_go.messages import (AMEND_EVENT_MESSAGE, AMEND_EVENT_MESSAGE_SIZE, CANCEL_EVENT_MESSAGE,
                                      CANCEL_EVENT_MESSAGE_SIZE, ERROR_MESSAGE, ERROR_MESSAGE_SIZE, HEADER_SIZE,
                                      HEDGE_EVENT_MESSAGE, HEDGE_EVENT_MESSAGE_SIZE, INSERT_EVENT_MESSAGE,
                                      INSERT_EVENT_MESSAGE_SIZE, LOGIN_EVENT_MESSAGE, LOGIN_EVENT_MESSAGE_SIZE,
                                      TRADE_EVENT_MESSAGE, TRADE_EVENT_MESSAGE_SIZE, MessageType)
from ready_trader_go.order_book import TOP_LEVEL_COUNT, Order, OrderBook
from ready_trader_go.types import Instrument, Lifespan, Side


__all__ = ("EventSource", "LiveEventSource", "RecordedEventSource")


TICK_INTERVAL_MILLISECONDS = 500
TICK_INTERVAL_SECONDS = TICK_INTERVAL_MILLISECONDS / 1000.0


class EventSource(QtCore.QObject):
    """A source of events for the Ready Trader Go HUD to display."""

    # Signals

    event_source_error_occurred = QtCore.Signal(str)  # error message

    login_occurred = QtCore.Signal(str)   # team

    match_over = QtCore.Signal()

    midpoint_price_changed = QtCore.Signal(Instrument, float, float)  # instrument, time, price in cents

    order_amended = QtCore.Signal(str, float, int, int)   # team, time, order_id, volume delta

    # instrument, time, ask prices, ask volumes, bid prices, bid volumes
    order_book_changed = QtCore.Signal(Instrument, float, list, list, list, list)

    order_cancelled = QtCore.Signal(str, float, int)  # team, time, order_id

    # team, time, order_id, instrument, side, volume, price, lifespan
    order_inserted = QtCore.Signal(str, float, int, Instrument, Side, int, int, Lifespan)

    # team, time, profit, etf position, account balance, total fees
    profit_loss_changed = QtCore.Signal(str, float, float, int, int, float, float)

    # team, time, order_id, side, volume, price, fee
    trade_occurred = QtCore.Signal(str, float, int, Side, int, int, int)

    def __init__(self, etf_clamp: float, tick_size: float, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)

        self._account_factory: AccountFactory = AccountFactory(etf_clamp, tick_size)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

    def _on_timer_tick(self) -> None:
        """Callback on timer ticks."""
        raise NotImplementedError()

    def start(self) -> None:
        """Start the event source."""
        raise NotImplementedError()


class LiveEventSource(EventSource):
    """An event source that receives events from an exchange simulator."""

    def __init__(self, host: str, port: int, etf_clamp: float, tick_size: float,
                 parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(etf_clamp, tick_size, parent)

        self.host: str = host
        self.port: int = port

        self.__accounts: Dict[int, CompetitorAccount] = dict()
        self.__now: float = 0.0
        self.__order_books: List[OrderBook] = list(OrderBook(i, 0.0, 0.0) for i in Instrument)
        self.__orders: Dict[int, Dict[int, Order]] = {0: dict()}
        self.__stop_later: bool = False
        self.__teams: Dict[int, str] = {0: ""}

        self.__ask_prices: List[int] = [0] * TOP_LEVEL_COUNT
        self.__ask_volumes: List[int] = [0] * TOP_LEVEL_COUNT
        self.__bid_prices: List[int] = [0] * TOP_LEVEL_COUNT
        self.__bid_volumes: List[int] = [0] * TOP_LEVEL_COUNT

        self.__socket = QtNetwork.QTcpSocket(self)
        self.__socket.connected.connect(self.on_connected)
        self.__socket.disconnected.connect(self.on_disconnected)
        self.__socket.errorOccurred.connect(self.on_error_occurred)
        self.__socket.readyRead.connect(self.on_data_received)
        self.__stream = QtCore.QDataStream(self.__socket)

    def __del__(self) -> None:
        """Destructor."""
        self.__socket.close()

    def on_connected(self) -> None:
        """Callback when a connection to the exchange is established."""
        self._timer.start(TICK_INTERVAL_MILLISECONDS)

    def on_disconnected(self) -> None:
        """Callback when the connection to the exchange is lost."""
        self.__stop_later = True

    def on_error_occurred(self, error: QtNetwork.QAbstractSocket.SocketError) -> None:
        """Callback when there is a problem with the exchange connection."""
        if error != QtNetwork.QAbstractSocket.SocketError.RemoteHostClosedError:
            self.event_source_error_occurred.emit(self.__socket.errorString())

    def on_data_received(self) -> None:
        """Callback when data is received from the exchange simulator."""
        while True:
            self.__stream.startTransaction()
            length: int = self.__stream.readUInt16()
            typ: int = self.__stream.readUInt8()
            data: bytes = self.__stream.readRawData(length - HEADER_SIZE)
            if not self.__stream.commitTransaction():
                return
            self.on_message(typ, data, length)

    def on_message(self, typ: int, data: bytes, length: int):
        """Process a message."""
        if typ == MessageType.AMEND_EVENT and length == AMEND_EVENT_MESSAGE_SIZE:
            self.on_amend_event_message(*AMEND_EVENT_MESSAGE.unpack_from(data))
        elif typ == MessageType.CANCEL_EVENT and length == CANCEL_EVENT_MESSAGE_SIZE:
            self.on_cancel_event_message(*CANCEL_EVENT_MESSAGE.unpack_from(data))
        elif typ == MessageType.INSERT_EVENT and length == INSERT_EVENT_MESSAGE_SIZE:
            self.on_insert_event_message(*INSERT_EVENT_MESSAGE.unpack_from(data))
        elif typ == MessageType.LOGIN_EVENT and length == LOGIN_EVENT_MESSAGE_SIZE:
            name, competitor_id = LOGIN_EVENT_MESSAGE.unpack_from(data)
            self.on_login_event_message(name.rstrip(b"\0").decode(), competitor_id)
        elif typ == MessageType.HEDGE_EVENT and length == HEDGE_EVENT_MESSAGE_SIZE:
            self.on_hedge_event_message(*HEDGE_EVENT_MESSAGE.unpack_from(data))
        elif typ == MessageType.TRADE_EVENT and length == TRADE_EVENT_MESSAGE_SIZE:
            self.on_trade_event_message(*TRADE_EVENT_MESSAGE.unpack_from(data))
        elif typ == MessageType.ERROR and length == ERROR_MESSAGE_SIZE:
            client_order_id, error_message = ERROR_MESSAGE.unpack_from(data)
            self.on_error_message(client_order_id, error_message.rstrip(b"\x00"))
        else:
            self.event_source_error_occurred.emit("received invalid message: length=%d type=%d" % (length, typ))

    def on_error_message(self, client_order_id: int, error_message: bytes):
        """Callback when an error message is received."""

    def on_amend_event_message(self, now: float, competitor_id: int, order_id: int, volume_delta: int) -> None:
        """Callback when an amend event message is received."""
        self.__now = now
        order = self.__orders[competitor_id].get(order_id)
        if order is not None:
            self.__order_books[order.instrument].amend(now, order, order.volume + volume_delta)
            if order.remaining_volume == 0:
                del self.__orders[competitor_id][order_id]
        if competitor_id != 0:
            self.order_amended.emit(self.__teams[competitor_id], now, order_id, volume_delta)

    def on_cancel_event_message(self, now: float, competitor_id: int, order_id: int) -> None:
        """Callback when an cancel event message is received."""
        self.__now = now
        order = self.__orders[competitor_id].pop(order_id, None)
        if order is not None:
            self.__order_books[order.instrument].cancel(now, order)
        if competitor_id != 0:
            self.order_cancelled.emit(self.__teams[competitor_id], now, order_id)

    def on_insert_event_message(self, now: float, competitor_id: int, order_id: int, instrument: int, side: int,
                                volume: int, price: int, lifespan: int) -> None:
        """Callback when an insert event message is received."""
        self.__now = now
        order = Order(order_id, Instrument(instrument), Lifespan(lifespan), Side(side), price, volume)
        self.__orders[competitor_id][order_id] = order
        self.__order_books[instrument].insert(now, order)
        if competitor_id != 0:
            self.order_inserted.emit(self.__teams[competitor_id], now, order_id, Instrument(instrument),
                                     Side(side), volume, price, Lifespan(lifespan))

    def on_hedge_event_message(self, now: float, competitor_id: int, side: int, instrument: int, volume: int,
                               price: float) -> None:
        """Callback when an hedge event message is received."""
        self.__now = now
        self.__accounts[competitor_id].transact(Instrument(instrument), Side(side), price, volume, 0)

    def on_login_event_message(self, name: str, competitor_id: int) -> None:
        """Callback when an login event message is received."""
        self.__accounts[competitor_id] = self._account_factory.create()
        self.__teams[competitor_id] = name
        self.__orders[competitor_id] = dict()
        self.login_occurred.emit(name)

    def _on_timer_tick(self):
        """Callback when the timer ticks."""
        if self.__now <= 0.0:
            return

        for i in Instrument:
            midpoint_price: float = self.__order_books[i].midpoint_price()
            if midpoint_price is not None:
                self.midpoint_price_changed.emit(i, self.__now, midpoint_price)
                self.__order_books[i].top_levels(self.__ask_prices, self.__ask_volumes, self.__bid_prices,
                                                 self.__bid_volumes)
                self.order_book_changed.emit(i, self.__now, self.__ask_prices, self.__ask_volumes,
                                             self.__bid_prices, self.__bid_volumes)

        future_price: int = self.__order_books[Instrument.FUTURE].last_traded_price()
        etf_price: int = self.__order_books[Instrument.ETF].last_traded_price()
        if future_price is None:
            future_price = round(self.__order_books[Instrument.FUTURE].midpoint_price())
        if future_price is not None and etf_price is not None:
            for competitor_id, account in self.__accounts.items():
                account.update(future_price, etf_price)
                self.profit_loss_changed.emit(self.__teams[competitor_id], self.__now,
                                              account.profit_or_loss / 100.0, account.etf_position,
                                              account.future_position, account.account_balance / 100.0,
                                              account.total_fees / 100.0)

        if self.__stop_later:
            self._timer.stop()
            self.match_over.emit()

    def on_trade_event_message(self, now: float, competitor_id: int, order_id: int, side: int, instrument: int,
                               volume: int, price: int, fee: int) -> None:
        """Callback when an trade event message is received."""
        self.__now = now
        self.__accounts[competitor_id].transact(Instrument(instrument), Side(side), price, volume, fee)
        self.trade_occurred.emit(self.__teams[competitor_id], now, order_id, Side(side), volume, price, fee)

        order = self.__orders[competitor_id].get(order_id)
        if order and order.remaining_volume == 0:
            del self.__orders[competitor_id][order_id]

    def start(self) -> None:
        """Start this live event source."""
        self.__socket.connectToHost(self.host, self.port)


class Event(NamedTuple):
    """A recorded event."""
    when: float
    emitter: Callable
    args: Tuple


class RecordedEventSource(EventSource):
    """A source of events taken from a recording of a match."""

    def __init__(self, etf_clamp: float, tick_size: float, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(etf_clamp, tick_size, parent)

        self.__teams: Set[str] = set()
        self.__end_time: float = 0.0
        self.__events: List[Event] = list()
        self.__event_iter: Optional[Iterator] = None
        self.__next_event: Optional[Event] = None
        self.__now: float = 0.0
        self.__order_books: Tuple[List[int], ...] = tuple(list() for _ in Instrument)

    def _on_timer_tick(self):
        """Callback when the timer ticks."""
        now = self.__now = self.__now + TICK_INTERVAL_SECONDS

        if self.__next_event.when <= now:
            self.__next_event.emitter(*self.__next_event.args)
            event: Optional[Event] = None
            for event in self.__event_iter:
                if event.when > now:
                    break
                event.emitter(*event.args)
            self.__next_event = event

        tick = int(now // TICK_INTERVAL_SECONDS)
        for i in Instrument:
            if len(self.__order_books[i]) >= (tick + 1) * 4 * TOP_LEVEL_COUNT:
                data = (self.__order_books[i][j * TOP_LEVEL_COUNT:(j + 1) * TOP_LEVEL_COUNT]
                        for j in range(tick * 4, (tick + 1) * 4))
                self.order_book_changed.emit(i, now, *data)

        if self.__now >= self.__end_time:
            self._timer.stop()
            self.match_over.emit()

    @staticmethod
    def from_csv(file_object: TextIO, etf_clamp: float, tick_size: float,
                 parent: Optional[QtCore.QObject] = None):
        """Create a new RecordedEventSource instance from a CSV file."""
        source = RecordedEventSource(etf_clamp, tick_size, parent)
        events = source.__events

        reader = csv.reader(file_object)
        next(reader)  # Skip header

        accounts: Dict[str, CompetitorAccount] = collections.defaultdict(source._account_factory.create)
        books: Tuple[OrderBook, ...] = tuple(OrderBook(i, 0.0, 0.0) for i in Instrument)
        orders: Dict[str, Dict[int, Order]] = collections.defaultdict(dict)

        ask_prices = [0] * TOP_LEVEL_COUNT
        ask_volumes = [0] * TOP_LEVEL_COUNT
        bid_prices = [0] * TOP_LEVEL_COUNT
        bid_volumes = [0] * TOP_LEVEL_COUNT

        def take_snapshot(when: float):
            for i in Instrument:
                events.append(Event(when, source.midpoint_price_changed.emit, (i, when, books[i].midpoint_price())))
                books[i].top_levels(ask_prices, ask_volumes, bid_prices, bid_volumes)
                source.__order_books[i].extend(itertools.chain(ask_prices, ask_volumes, bid_prices, bid_volumes))

            future_price: int = books[Instrument.FUTURE].last_traded_price()
            etf_price: int = books[Instrument.ETF].last_traded_price()
            if future_price is not None and etf_price is not None:
                for team, account in accounts.items():
                    account.update(future_price, etf_price)
                    events.append(Event(when, source.profit_loss_changed.emit,
                                        (team, when, account.profit_or_loss / 100.0, account.etf_position,
                                         account.future_position, account.account_balance / 100.0,
                                         account.total_fees / 100.0)))

        now: float = TICK_INTERVAL_SECONDS
        for row in reader:
            tm = float(row[0])

            if tm > now:
                take_snapshot(now)
                now += TICK_INTERVAL_SECONDS

            team: str = row[1]
            order_id: int = int(row[3])
            operation: str = row[2]

            if team and team not in source.__teams:
                source.__teams.add(team)

            if operation == "Insert":
                order = Order(order_id, Instrument(int(row[4])), Lifespan[row[8]], Side[row[5]],
                              int(row[7]), int(row[6]))
                books[order.instrument].insert(tm, order)
                orders[team][order_id] = order
                events.append(Event(tm, source.order_inserted.emit, (team, tm, order_id, order.instrument,
                                                                     order.side, order.volume, order.price,
                                                                     order.lifespan)))
            elif operation == "Amend":
                order = orders[team][order_id]
                volume_delta = int(row[6])
                books[order.instrument].amend(tm, order, order.volume + volume_delta)
                if order.remaining_volume == 0:
                    del orders[team][order_id]
                events.append(Event(tm, source.order_amended.emit, (team, tm, order_id, volume_delta)))
            elif operation == "Cancel":
                order = orders[team].pop(order_id, None)
                if order:
                    books[order.instrument].cancel(tm, order)
                events.append(Event(tm, source.order_cancelled.emit, (team, tm, order_id)))
            else:  # operation is "Hedge" or "Trade"
                instrument = Instrument(int(row[4]))
                side = Side[row[5]]
                volume = int(row[6])
                price = float(row[7]) if operation == "Hedge" else int(row[7])
                fee = int(row[9]) if row[9] else 0
                accounts[team].transact(instrument, side, price, volume, fee)
                if operation == "Trade":
                    if order_id in orders[team] and orders[team][order_id].remaining_volume == 0:
                        del orders[team][order_id]
                    events.append(Event(tm, source.trade_occurred.emit, (team, tm, order_id, side, volume, price,
                                                                         fee)))

        take_snapshot(now)
        source.__end_time = now

        return source

    def start(self) -> None:
        """Start this recorded event source."""
        self.__now = 0.0
        self._timer.start(TICK_INTERVAL_MILLISECONDS)
        self.__event_iter = iter(self.__events)
        self.__next_event = next(self.__event_iter, None)
        for competitor in sorted(self.__teams):
            self.login_occurred.emit(competitor)
