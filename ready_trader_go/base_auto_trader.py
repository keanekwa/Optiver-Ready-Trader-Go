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

from typing import List, Optional

from .messages import (AMEND_MESSAGE, AMEND_MESSAGE_SIZE, CANCEL_MESSAGE, CANCEL_MESSAGE_SIZE,
                       ERROR_MESSAGE, ERROR_MESSAGE_SIZE, HEDGE_MESSAGE, HEDGE_MESSAGE_SIZE,
                       HEDGE_FILLED_MESSAGE, HEDGE_FILLED_MESSAGE_SIZE, INSERT_MESSAGE, INSERT_MESSAGE_SIZE,
                       LOGIN_MESSAGE, LOGIN_MESSAGE_SIZE, ORDER_BOOK_HEADER, ORDER_BOOK_HEADER_SIZE,
                       ORDER_BOOK_MESSAGE_SIZE, BOOK_PART, ORDER_FILLED_MESSAGE, ORDER_FILLED_MESSAGE_SIZE,
                       ORDER_STATUS_MESSAGE, ORDER_STATUS_MESSAGE_SIZE, TRADE_TICKS_HEADER,
                       TRADE_TICKS_HEADER_SIZE, TRADE_TICKS_MESSAGE_SIZE, TICKS_PART,
                       Connection, MessageType, Subscription)
from .types import Lifespan, Side


class BaseAutoTrader(Connection, Subscription):
    """Base class for an auto-trader."""

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the BaseTraderProtocol class."""
        Connection.__init__(self)
        Subscription.__init__(self)

        self.event_loop: asyncio.AbstractEventLoop = loop
        self.logger = logging.getLogger("TRADER")
        self.team_name: bytes = team_name.encode()
        self.secret: bytes = secret.encode()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called twice, when the execution connection and the information channel are established."""
        if transport.get_extra_info("peername") is not None:
            Connection.connection_made(self, transport)
            self.send_message(MessageType.LOGIN, LOGIN_MESSAGE.pack(self.team_name, self.secret), LOGIN_MESSAGE_SIZE)
        else:
            Subscription.connection_made(self, transport)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when the connection is lost on the execution channel."""
        if self._connection_transport is not None and self._connection_transport.is_closing():
            Connection.connection_lost(self, exc)
            Subscription.close(self)
        else:
            Subscription.connection_lost(self, exc)
            Connection.close(self)
        self.event_loop.stop()

    def on_datagram(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Called when an information message is received from the matching engine."""
        if typ == MessageType.ORDER_BOOK_UPDATE and length == ORDER_BOOK_MESSAGE_SIZE:
            inst, seq = ORDER_BOOK_HEADER.unpack_from(data, start)
            self.on_order_book_update_message(inst, seq, *BOOK_PART.iter_unpack(data[ORDER_BOOK_HEADER_SIZE:]))
        elif typ == MessageType.TRADE_TICKS and length == TRADE_TICKS_MESSAGE_SIZE:
            inst, seq = TRADE_TICKS_HEADER.unpack_from(data, start)
            self.on_trade_ticks_message(inst, seq, *TICKS_PART.iter_unpack(data[TRADE_TICKS_HEADER_SIZE:]))
        else:
            self.logger.error("received invalid information message: length=%d type=%d", length, typ)
            self.event_loop.stop()

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled, partially or fully.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """

    def on_message(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Called when an execution message is received from the matching engine."""
        if typ == MessageType.ERROR and length == ERROR_MESSAGE_SIZE:
            client_order_id, error_message = ERROR_MESSAGE.unpack_from(data, start)
            self.on_error_message(client_order_id, error_message.rstrip(b"\x00"))
        elif typ == MessageType.HEDGE_FILLED and length == HEDGE_FILLED_MESSAGE_SIZE:
            self.on_hedge_filled_message(*HEDGE_FILLED_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.ORDER_FILLED and length == ORDER_FILLED_MESSAGE_SIZE:
            self.on_order_filled_message(*ORDER_FILLED_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.ORDER_STATUS and length == ORDER_STATUS_MESSAGE_SIZE:
            self.on_order_status_message(*ORDER_STATUS_MESSAGE.unpack_from(data, start))
        else:
            self.logger.error("received invalid execution message: length=%d type=%d", length, typ)
            self.event_loop.stop()

    def on_error_message(self, client_order_id: int, error_message: bytes):
        """Called when the matching engine detects an error."""

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of the order book.

        The sequence number can be used to detect missed messages. The five
        best available ask (i.e. sell) and bid (i.e. buy) prices are reported
        along with the volume available at each of those price levels. If
        there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes lists on that side so that
        there are always five entries in each list.
        """

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the total number of lots already traded,
        remaining_volume is the number of lots yet to be traded and fees is
        the total fees paid or received for this order.

        Remaining volume will be set to zero if the order is cancelled.
        """

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the volume traded at
        each of those price levels. If there are less than five prices on a
        side, then zeros will appear at the end of both the prices and volumes
        lists on that side so that there are always five entries in each list.
        """

    def send_amend_order(self, client_order_id: int, volume: int) -> None:
        """Amend the specified order with an updated volume.

        The specified volume must be no greater than the original volume for
        the order. If the order has already completely filled or been
        cancelled this request has no effect and no order status message will
        be received.
        """
        self.send_message(MessageType.AMEND_ORDER, AMEND_MESSAGE.pack(client_order_id, volume), AMEND_MESSAGE_SIZE)

    def send_cancel_order(self, client_order_id: int) -> None:
        """Cancel the specified order.

        If the order has already completely filled or been cancelled this
        request has no effect and no order status message will be received.
        """
        self.send_message(MessageType.CANCEL_ORDER, CANCEL_MESSAGE.pack(client_order_id), CANCEL_MESSAGE_SIZE)

    def send_hedge_order(self, client_order_id: int, side: Side, price: int, volume: int) -> None:
        """Order lots in the future to hedge a position."""
        self.send_message(MessageType.HEDGE_ORDER,
                          HEDGE_MESSAGE.pack(client_order_id, side, price, volume),
                          HEDGE_MESSAGE_SIZE)

    def send_insert_order(self, client_order_id: int, side: Side, price: int, volume: int, lifespan: Lifespan) -> None:
        """Insert a new order into the market."""
        self.send_message(MessageType.INSERT_ORDER,
                          INSERT_MESSAGE.pack(client_order_id, side, price, volume, lifespan),
                          INSERT_MESSAGE_SIZE)
