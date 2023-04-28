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
import select
import socket

from typing import Dict, List

from ready_trader_go.messages import *
from ready_trader_go.types import Lifespan, Side


class Fill:
    def __init__(self, price: int, volume: int):
        """Initialise a new instance of the class."""
        self.price = price
        self.volume = volume

    def __repr__(self) -> str:
        return "Fill(price=%d, volume=%d)" % (self.price, self.volume)

    def __str__(self) -> str:
        return "%d lots at %.2f" % (self.volume, self.price / 100.0)


class Order:
    def __init__(self, order_id: int, side: Side, price_in_cents: int, volume: int, lifespan: Lifespan):
        """Initialise a new instance of the class."""
        self.order_id = order_id
        self.side = side
        self.price = price_in_cents
        self.volume = volume
        self.lifespan = lifespan

        self.fills: List[Fill] = list()
        self.fill_volume: int = 0
        self.remaining_volume: int = volume
        self.total_fees: int = 0

    def __repr__(self) -> str:
        result = "Order(order_id=%d, side=%s, price_in_cents=%d, volume=%d, lifespan=%s)"
        return result % (self.order_id, self.side, self.price, self.volume, self.lifespan)

    def __str__(self) -> str:
        result = "%s\n  fill volume: %d\n  remaining volume: %d\n  total fees: %.2f\n  fills: %s"
        return result % (repr(self), self.fill_volume, self.remaining_volume, self.total_fees/100.0, str(self.fills))


class DemoClient:
    """A Ready Trader Go exchange client for Jupyter Notebooks."""

    def __init__(self, name: str, secret: str):
        """Initialise a new instance of the class."""
        self.name: str = name
        self.secret: str = secret

        self.__buffer = bytearray()
        self.__last_order_id: int = 0
        self.__orders: Dict = dict()
        self.__sock: Optional[socket.socket] = None

    @staticmethod
    def display_error(message: str) -> None:
        """Display an error message."""
        print("An error has occurred: %s\n"
              "Please quit and restart Ready Trader Go and restart this Jupyter notebook." % message)

    def connect(self, host: str = "127.0.0.1", port: int = 12345) -> None:
        """Connect to the exchange simulator.

        The arguments specify the network address of the exchange simulator.
        """
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.__sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self.__sock.connect((host, port))
        except OSError as e:
            print("Connect failed: %s" % e.strerror)
            return
        self.__sock.setblocking(False)
        self.__sock.send(HEADER.pack(LOGIN_MESSAGE_SIZE, MessageType.LOGIN)
                         + LOGIN_MESSAGE.pack(self.name.encode(), self.secret.encode()))

    def get_order(self, order_id: int) -> Order:
        """Return the specified order.

        Raises a KeyError if the order does not exist.
        """
        return self.__orders[order_id]

    def send_amend_order(self, order_id: int, new_volume: int) -> None:
        """Amend the specified order.

        The new volume must be less than or equal to the original volume.
        """
        self.__sock.send(HEADER.pack(AMEND_MESSAGE_SIZE, MessageType.AMEND_ORDER)
                         + AMEND_MESSAGE.pack(order_id, new_volume))

    def send_cancel_order(self, order_id: int) -> None:
        """Cancel the specified order."""
        self.__sock.send(HEADER.pack(CANCEL_MESSAGE_SIZE, MessageType.CANCEL_ORDER)
                         + CANCEL_MESSAGE.pack(order_id))

    def send_insert_order(self, order_id: int, side: Side, price_in_cents: int, volume: int,
                          lifespan: Lifespan) -> Order:
        """Insert a new order and return an Order instance.

        The order_id should be a unique order identifier, the side should be
        either Side.BUY or Side.SELL, the price should be the limit price for
        the order, the volume should be the number of lots to trade and
        lifespan should be either Lifespan.GOOD_FOR_DAY or
        Lifespan.FILL_AND_KILL.
        """
        if order_id <= self.__last_order_id:
            raise ValueError("order_id must be greater than 0 and greater than the last order id")
        self.__sock.send(HEADER.pack(INSERT_MESSAGE_SIZE, MessageType.INSERT_ORDER)
                         + INSERT_MESSAGE.pack(order_id, side, price_in_cents, volume, lifespan))
        self.__orders[order_id] = Order(order_id, side, price_in_cents, volume, lifespan)
        return self.__orders[order_id]

    def update_orders(self) -> None:
        """Process messages from the exchange and update orders."""
        try:
            ready, _, _ = select.select([self.__sock], [self.__sock], [], 0)
        except select.error as e:
            self.display_error(str(e))
            return

        if ready:
            data = self.__sock.recv(4096)
            if len(data) == 0:
                self.display_error("connection to exchange simulator lost")
                return

            self.__buffer += data

            upto: int = 0
            data_length: int = len(self.__buffer)

            while upto < data_length - HEADER_SIZE:
                length, typ = HEADER.unpack_from(self.__buffer, upto)
                if upto + length > data_length:
                    break
                self.__on_message(typ, self.__buffer, upto + HEADER_SIZE, length)
                upto += length

            self.__buffer = self.__buffer[upto:]

    @staticmethod
    def __on_error_message(order_id: int, message: bytes) -> None:
        if order_id != 0:
            print("Error with order %d: %s" % (order_id, message.decode()))
        else:
            print("Error reported: %s" % message.decode())

    def __on_message(self, typ: int, data: bytearray, start: int, length: int) -> None:
        if typ == MessageType.ERROR and length == ERROR_MESSAGE_SIZE:
            client_order_id, error_message = ERROR_MESSAGE.unpack_from(data, start)
            self.__on_error_message(client_order_id, error_message.rstrip(b"\x00"))
        elif typ == MessageType.ORDER_FILLED and length == ORDER_FILLED_MESSAGE_SIZE:
            self.__on_order_filled_message(*ORDER_FILLED_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.ORDER_STATUS and length == ORDER_STATUS_MESSAGE_SIZE:
            self.__on_order_status_message(*ORDER_STATUS_MESSAGE.unpack_from(data, start))
        else:
            print("received invalid message: length=%d type=%d", length, typ)

    def __on_order_filled_message(self, order_id: int, price: int, volume: int) -> None:
        order: Order = self.__orders[order_id]
        order.fills.append(Fill(price, volume))

    def __on_order_status_message(self, order_id: int, fill_volume: int, remaining_volume: int,
                                  fees: int) -> None:
        order: Order = self.__orders[order_id]
        order.fill_volume = fill_volume
        order.remaining_volume = remaining_volume
        order.total_fees = fees
