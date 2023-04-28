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
import bisect
import logging

from typing import Any, Callable, Dict, Iterable, List, Optional

from .account import AccountFactory, CompetitorAccount
from .match_events import MatchEvents
from .order_book import IOrderListener, Order, OrderBook, MINIMUM_BID, MAXIMUM_ASK
from .score_board import ScoreBoardWriter
from .timer import Timer
from .types import ICompetitor, IController, IExecutionConnection, Instrument, Lifespan, Side
from .unhedged_lots import UnhedgedLots, UnhedgedLotsFactory


class Competitor(ICompetitor, IOrderListener):
    """A competitor in the Ready Trader Go competition."""

    def __init__(self, name: str, exec_channel: IExecutionConnection, etf_book: OrderBook, future_book: OrderBook,
                 account: CompetitorAccount, match_events: MatchEvents, score_board: ScoreBoardWriter,
                 position_limit: int, order_count_limit: int, active_volume_limit: int, tick_size: float,
                 unhedged_lots_factory: UnhedgedLotsFactory, controller: IController):
        """Initialise a new instance of the Competitor class."""
        self.account: CompetitorAccount = account
        self.active_volume: int = 0
        self.active_volume_limit: int = active_volume_limit
        self.controller: IController = controller
        self.etf_book: OrderBook = etf_book
        self.future_book: OrderBook = future_book
        self.buy_prices: List[int] = list()
        self.exec_connection: IExecutionConnection = exec_channel
        self.last_client_order_id: int = -1
        self.logger: logging.Logger = logging.getLogger("COMPETITOR")
        self.match_events: MatchEvents = match_events
        self.order_count_limit: int = order_count_limit
        self.name: str = name
        self.orders: Dict[int, Order] = dict()
        self.position_limit: int = position_limit
        self.score_board: ScoreBoardWriter = score_board
        self.sell_prices: List[int] = list()
        self.status: str = "OK"
        self.tick_size: int = int(tick_size * 100.0)  # convert tick size to cents
        self.unhedged_etf_lots: UnhedgedLots = unhedged_lots_factory.create(self.on_unhedged_lots_expiry)

    def disconnect(self, now: float) -> None:
        """Disconnect this competitor."""
        if self.exec_connection is not None:
            self.logger.info("'%s' closing execution channel at time=%.6f", self.name, now)
            self.exec_connection.close()

    def hard_breach(self, now: float, client_order_id: int, message: bytes) -> None:
        """Handle a hard breach by this competitor."""
        self.status = "BREACH"
        self.score_board.breach(now, self.name, self.account, self.etf_book.last_traded_price(),
                                self.future_book.last_traded_price())
        if self.exec_connection is not None:
            self.send_error_and_close(now, client_order_id, message)

    def on_connection_lost(self, now: float) -> None:
        """Called when the connection to the matching engine is lost."""
        self.exec_connection = None
        self.score_board.disconnect(now, self.name, self.account, self.etf_book.last_traded_price(),
                                    self.future_book.last_traded_price())
        for o in tuple(self.orders.values()):
            self.etf_book.cancel(now, o)

    # IOrderListener callbacks
    def on_order_amended(self, now: float, order: Order, volume_removed: int) -> None:
        """Called when an order is amended."""
        if self.exec_connection is not None:
            self.exec_connection.send_order_status(order.client_order_id, order.volume - order.remaining_volume,
                                                   order.remaining_volume, order.total_fees)
        self.match_events.amend(now, self.name, order.client_order_id, -volume_removed)

        self.active_volume -= volume_removed

        if order.remaining_volume == 0:
            del self.orders[order.client_order_id]
            if order.side == Side.BUY:
                self.buy_prices.pop(bisect.bisect(self.buy_prices, order.price) - 1)
            else:
                self.sell_prices.pop(bisect.bisect(self.sell_prices, -order.price) - 1)

    def on_order_cancelled(self, now: float, order: Order, volume_removed: int) -> None:
        """Called when an order is cancelled."""
        if self.exec_connection is not None:
            self.exec_connection.send_order_status(order.client_order_id, order.volume - volume_removed,
                                                   order.remaining_volume, order.total_fees)
        self.match_events.cancel(now, self.name, order.client_order_id, -volume_removed)

        self.active_volume -= volume_removed

        del self.orders[order.client_order_id]
        if order.side == Side.BUY:
            self.buy_prices.pop(bisect.bisect(self.buy_prices, order.price) - 1)
        else:
            self.sell_prices.pop(bisect.bisect(self.sell_prices, -order.price) - 1)

    def on_order_placed(self, now: float, order: Order) -> None:
        """Called when a good-for-day order is placed in the order book."""
        # Only send an order status if the order has not partially filled
        if order.volume == order.remaining_volume and self.exec_connection is not None:
            self.exec_connection.send_order_status(order.client_order_id, 0, order.remaining_volume, order.total_fees)

    def on_order_filled(self, now: float, order: Order, price: int, volume: int, fee: int) -> None:
        """Called when an order is partially or completely filled."""
        self.active_volume -= volume

        if order.remaining_volume == 0:
            del self.orders[order.client_order_id]
            if order.side == Side.BUY:
                self.buy_prices.pop()
            else:
                self.sell_prices.pop()

        self.unhedged_etf_lots.apply_position_delta(volume if order.side == Side.BUY else -volume)

        self.match_events.fill(now, self.name, order.client_order_id, order.instrument, order.side, price, volume, fee)
        last_traded: int = self.future_book.last_traded_price() or round(self.future_book.midpoint_price())
        self.account.transact(Instrument.ETF, order.side, price, volume, fee)
        self.account.update(last_traded, price)

        if self.exec_connection is not None:
            self.exec_connection.send_order_filled(order.client_order_id, price, volume)
            self.exec_connection.send_order_status(order.client_order_id, order.volume - order.remaining_volume,
                                                   order.remaining_volume, order.total_fees)

        if not (-self.position_limit <= self.account.etf_position <= self.position_limit):
            self.hard_breach(now, order.client_order_id, b"ETF position limit breached")

    def on_unhedged_lots_expiry(self):
        """Called when unhedged lots have been held for too long."""
        self.logger.info("Unhedged lots timer expired for %s at etf=%d fut=%d rel=%d", self.name,
                         self.account.etf_position, self.account.future_position,
                         self.unhedged_etf_lots.relative_position)

        now: float = self.controller.advance_time()
        self.hard_breach(now, 0, b"held unhedged lots for longer than the time limit")

    # Message callbacks
    def on_amend_message(self, now: float, client_order_id: int, volume: int) -> None:
        """Called when an amend order request is received from the competitor."""
        if client_order_id > self.last_client_order_id:
            self.send_error(now, client_order_id, b"out-of-order client_order_id in amend message")
            return

        if client_order_id in self.orders:
            order = self.orders[client_order_id]
            if volume > order.volume:
                self.send_error(now, client_order_id, b"amend operation would increase order volume")
            else:
                self.etf_book.amend(now, order, volume)

    def on_cancel_message(self, now: float, client_order_id: int) -> None:
        """Called when a cancel order request is received from the competitor."""
        if client_order_id > self.last_client_order_id:
            self.send_error(now, client_order_id, b"out-of-order client_order_id in cancel message")
            return

        if client_order_id in self.orders:
            self.etf_book.cancel(now, self.orders[client_order_id])

    def on_hedge_message(self, now: float, client_order_id: int, side: int, price: int, volume: int) -> None:
        """Called when a hedge order request is received from the competitor."""
        if client_order_id <= self.last_client_order_id:
            self.send_error(now, client_order_id, b"duplicate or out-of-order client_order_id")
            return

        self.last_client_order_id = client_order_id

        if side != Side.BUY and side != Side.SELL:
            self.send_error(now, client_order_id, b"%d is not a valid side" % side)
            return

        if not (MINIMUM_BID <= price <= MAXIMUM_ASK):
            self.send_error(now, client_order_id, b"%d is not a valid price" % price)
            return

        if price % self.tick_size != 0:
            self.send_error(now, client_order_id, b"price is not a multiple of tick size")
            return

        if volume < 1:
            self.send_error(now, client_order_id, b"%d is not a valid volume" % volume)
            return

        if now == 0.0:
            self.send_error(now, client_order_id, b"order rejected: market not yet open")
            return

        side_: Side = Side(side)
        volume_traded, average_price = self.future_book.try_trade(side_, price, volume)
        if volume_traded == 0:
            # The trade could have failed because there were no orders on the opposite side
            best: Optional[int] = self.future_book.best_ask() if side_ == Side.BID else self.future_book.best_bid()
            if best is None:
                last_traded = self.future_book.last_traded_price()
                if last_traded is None:
                    self.send_error(now, client_order_id, b"order rejected: cannot determine future price")
                    return
                if (side_ == Side.ASK and last_traded >= price) or (side_ == Side.BID and last_traded <= price):
                    average_price = last_traded

        if average_price == 0:
            if self.exec_connection is not None:
                self.exec_connection.send_hedge_filled(client_order_id, 0, 0)
            return

        self.unhedged_etf_lots.apply_position_delta(volume if side_ == Side.BID else -volume)
        self.match_events.hedge(now, self.name, client_order_id, Instrument.FUTURE, side_, average_price,
                                volume)
        self.account.transact(Instrument.FUTURE, side_, average_price, volume, 0)
        self.account.update(self.future_book.last_traded_price() or self.future_book.midpoint_price(),
                            self.etf_book.last_traded_price() or self.etf_book.midpoint_price())

        if self.exec_connection is not None:
            self.exec_connection.send_hedge_filled(client_order_id, average_price, volume)

        if not (-self.position_limit <= self.account.future_position <= self.position_limit):
            self.hard_breach(now, client_order_id, b"future position limit breached")

    def on_insert_message(self, now: float, client_order_id: int, side: int, price: int, volume: int,
                          lifespan: int) -> None:
        """Called when an insert order request is received from the competitor."""
        if client_order_id <= self.last_client_order_id:
            self.send_error(now, client_order_id, b"duplicate or out-of-order client_order_id")
            return

        self.last_client_order_id = client_order_id

        if side != Side.BUY and side != Side.SELL:
            self.send_error(now, client_order_id, b"%d is not a valid side" % side)
            return

        if lifespan != Lifespan.FILL_AND_KILL and lifespan != Lifespan.GOOD_FOR_DAY:
            self.send_error(now, client_order_id, b"%d is not a valid lifespan" % lifespan)
            return

        if not (MINIMUM_BID <= price <= MAXIMUM_ASK):
            self.send_error(now, client_order_id, b"%d is not a valid price" % price)
            return

        if price % self.tick_size != 0:
            self.send_error(now, client_order_id, b"price is not a multiple of tick size")
            return

        if len(self.orders) == self.order_count_limit:
            self.send_error(now, client_order_id, b"order rejected: active order count limit breached")
            return

        if volume < 1:
            self.send_error(now, client_order_id, b"%d is not a valid volume")
            return

        if self.active_volume + volume > self.active_volume_limit:
            self.send_error(now, client_order_id, b"order rejected: active order volume limit breached")
            return

        if now == 0.0:
            self.send_error(now, client_order_id, b"order rejected: market not yet open")
            return

        if ((side == Side.BUY and self.sell_prices and price >= -self.sell_prices[-1])
                or (side == Side.SELL and self.buy_prices and price <= self.buy_prices[-1])):
            self.send_error(now, client_order_id, b"order rejected: in cross with an existing order")
            return

        order = self.orders[client_order_id] = Order(client_order_id, Instrument.ETF, Lifespan(lifespan), Side(side),
                                                     price, volume, self)
        if side == Side.BUY:
            bisect.insort(self.buy_prices, price)
        else:
            bisect.insort(self.sell_prices, -price)
        self.match_events.insert(now, self.name, order.client_order_id, order.instrument, order.side, order.volume,
                                 order.price, order.lifespan)
        self.active_volume += volume
        self.etf_book.insert(now, order)

    def on_timer_tick(self, now: float, future_price: int, etf_price: int) -> None:
        """Called on each timer tick to update the auto-trader."""
        self.account.update(future_price or 0, etf_price or 0)
        self.score_board.tick(now, self.name, self.account, etf_price, future_price, self.status)

    def send_error(self, now: float, client_order_id: int, message: bytes) -> None:
        """Send an error message to the auto-trader and shut down the match."""
        self.exec_connection.send_error(client_order_id, message)
        self.logger.info("'%s' sent error message: time=%.6f client_order_id=%s message='%s'", self.name, now,
                         client_order_id, message.decode())

    def send_error_and_close(self, now: float, client_order_id: int, message: bytes) -> None:
        """Send an error message to the auto-trader and shut down the match."""
        self.send_error(now, client_order_id, message)
        self.logger.info("'%s' closing execution channel at time=%.6f", self.name, now)
        self.exec_connection.close()


class CompetitorManager:
    """A manager of competitors."""

    def __init__(self, limits_config: Dict[str, Any], traders_config: Dict[str, str], account_factory: AccountFactory,
                 etf_book: OrderBook, future_book: OrderBook, match_events: MatchEvents,
                 score_board_writer: ScoreBoardWriter, tick_size: float, timer: Timer,
                 unhedged_lots_factory: UnhedgedLotsFactory):
        """Initialise a new instance of the CompetitorManager class."""
        self.__account_factory: AccountFactory = account_factory
        self.__active_volume_limit: int = limits_config["ActiveVolumeLimit"]
        self.__competitors: Dict[str, Competitor] = dict()
        self.__etf_book: OrderBook = etf_book
        self.__future_book: OrderBook = future_book
        self.__logger: logging.Logger = logging.getLogger("COMPETITOR")
        self.__match_events: MatchEvents = match_events
        self.__order_count_limit: int = limits_config["ActiveOrderCountLimit"]
        self.__position_limit: int = limits_config["PositionLimit"]
        self.__score_board_writer: ScoreBoardWriter = score_board_writer
        self.__start_time: float = 0.0
        self.__traders: Dict[str, str] = traders_config
        self.__unhedged_lots_factory: UnhedgedLotsFactory = unhedged_lots_factory
        self.__tick_size: float = tick_size

        self.active_competitor_count: int = 0
        self.controller: Optional[IController] = None
        self.competitor_logged_in: List[Callable[[str], None]] = list()

        timer.timer_started.append(self.on_timer_started)
        timer.timer_stopped.append(self.on_timer_stopped)
        timer.timer_ticked.append(self.on_timer_tick)

    def get_competitors(self) -> Iterable[Competitor]:
        """Return an iterable of the competitors managed by this CompetitorManager."""
        return self.__competitors.values()

    def login_competitor(self, name: str, secret: str, exec_channel: IExecutionConnection) -> Optional[ICompetitor]:
        """Return the competitor object for the given name."""
        if name in self.__competitors or name not in self.__traders or self.__traders[name] != secret:
            return None

        competitor = Competitor(name, exec_channel, self.__etf_book, self.__future_book,
                                self.__account_factory.create(), self.__match_events, self.__score_board_writer,
                                self.__position_limit, self.__order_count_limit, self.__active_volume_limit,
                                self.__tick_size, self.__unhedged_lots_factory, self.controller)
        self.__competitors[name] = competitor

        if self.__start_time != 0.0:
            self.__logger.warning("competitor logged in after market open: name='%s'", name)

        for callback in self.competitor_logged_in:
            callback(name)

        return competitor

    def on_competitor_connect(self) -> None:
        """Notify this competitor manager that a competitor has connected."""
        self.active_competitor_count += 1

    def on_competitor_disconnect(self) -> None:
        """Notify this competitor manager that a competitor has disconnected."""
        self.active_competitor_count -= 1

    def on_timer_started(self, _: Timer, start_time: float) -> None:
        """Called when the market opens."""
        self.__start_time = start_time

    def on_timer_stopped(self, _: Timer, end_time: float) -> None:
        """Called when the market closes."""
        for competitor in self.__competitors.values():
            competitor.disconnect(end_time)

    def on_timer_tick(self, timer: Timer, now: float, _: int) -> None:
        """Called on each timer tick."""
        etf_price = self.__etf_book.last_traded_price()
        future_price = self.__future_book.last_traded_price()
        for competitor in self.__competitors.values():
            competitor.on_timer_tick(now, future_price, etf_price)

        if self.active_competitor_count == 0:
            timer.shutdown(now, "no remaining competitors")
