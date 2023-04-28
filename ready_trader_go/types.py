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
import enum


class Instrument(enum.IntEnum):
    FUTURE = 0
    ETF = 1


class Side(enum.IntEnum):
    SELL = 0
    BUY = 1
    ASK = SELL
    BID = BUY
    A = SELL
    B = BUY


class Lifespan(enum.IntEnum):
    FILL_AND_KILL = 0  # Fill and kill orders trade immediately if possible, otherwise they are cancelled
    GOOD_FOR_DAY = 1  # Good for day orders remain in the market until they trade or are explicitly cancelled
    IMMEDIATE_OR_CANCEL = FILL_AND_KILL
    LIMIT_ORDER = GOOD_FOR_DAY
    FAK = FILL_AND_KILL
    GFD = GOOD_FOR_DAY
    F = FILL_AND_KILL
    G = GOOD_FOR_DAY


class ICompetitor:
    def disconnect(self, now: float) -> None:
        """Disconnect this competitor."""
        raise NotImplementedError()

    def on_amend_message(self, now: float, client_order_id: int, volume: int) -> None:
        """Called when an amend order request is received from the competitor."""
        raise NotImplementedError()

    def on_cancel_message(self, now: float, client_order_id: int) -> None:
        """Called when a cancel order request is received from the competitor."""
        raise NotImplementedError()

    def on_hedge_message(self, now: float, client_order_id: int, side: int, price: int, volume: int) -> None:
        """Called when a hedge order request is received from the competitor."""
        raise NotImplementedError

    def on_insert_message(self, now: float, client_order_id: int, side: int, price: int, volume: int,
                          lifespan: int) -> None:
        """Called when an insert order request is received from the competitor."""
        raise NotImplementedError()


class IController:
    def advance_time(self):
        """Return the current time after accounting for events."""
        raise NotImplementedError()


class IExecutionConnection:
    def close(self):
        """Close the execution channel."""
        raise NotImplementedError()

    def send_error(self, client_order_id: int, error_message: bytes) -> None:
        """Send an error message to the auto-trader."""
        raise NotImplementedError()

    def send_hedge_filled(self, client_order_id: int, average_price: int, volume: int) -> None:
        """Send a hedge filled message to the auto-trader."""

    def send_order_filled(self, client_order_id: int, price: int, volume: int) -> None:
        """Send an order filled message to the auto-trader."""
        raise NotImplementedError()

    def send_order_status(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Send an order status message to the auto-trader."""
        raise NotImplementedError()
