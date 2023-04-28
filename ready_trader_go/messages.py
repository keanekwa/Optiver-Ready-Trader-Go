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
import enum
import logging
import struct

from typing import Optional, Tuple

import ready_trader_go.order_book as order_book


@enum.unique
class MessageType(enum.IntEnum):
    # Execution messages
    AMEND_ORDER = 1
    CANCEL_ORDER = 2
    ERROR = 3
    HEDGE_FILLED = 4
    HEDGE_ORDER = 5
    INSERT_ORDER = 6
    LOGIN = 7
    ORDER_FILLED = 8
    ORDER_STATUS = 9

    # Information messages
    ORDER_BOOK_UPDATE = 10
    TRADE_TICKS = 11

    # Heads Up Display messages
    AMEND_EVENT = 100
    CANCEL_EVENT = 101
    INSERT_EVENT = 102
    HEDGE_EVENT = 103
    LOGIN_EVENT = 104
    TRADE_EVENT = 105


# Standard message header: message length (2 bytes) and type (1 byte)
HEADER = struct.Struct("!HB")  # Length, message type

# Auto-trader to matching engine messages
AMEND_MESSAGE = struct.Struct("!II")  # Client order id and new volume
CANCEL_MESSAGE = struct.Struct("!I")  # Client order id
HEDGE_MESSAGE = struct.Struct("!IBII")  # Client order id, side, price, volume
INSERT_MESSAGE = struct.Struct("!IBIIB")  # Client order id, side, price, volume and lifespan
LOGIN_MESSAGE = struct.Struct("!50s50s")  # Name, secret

# Matching engine to auto-trader messages
ERROR_MESSAGE = struct.Struct("!I50s")  # message
HEDGE_FILLED_MESSAGE = struct.Struct("!III")  # Client order id, price, volume
ORDER_BOOK_HEADER = struct.Struct("!BI")  # Instrument and sequence number
ORDER_BOOK_MESSAGE = struct.Struct("!%dI" % (4 * order_book.TOP_LEVEL_COUNT))  # Prices & volumes for best bids & asks
ORDER_FILLED_MESSAGE = struct.Struct("!III")  # Client order id, price, volume
ORDER_STATUS_MESSAGE = struct.Struct("!IIIi")  # Client order id, fill volume, remaining volume and fees
TRADE_TICKS_HEADER = struct.Struct("!BI")  # Instrument and sequence number
TRADE_TICKS_MESSAGE = struct.Struct("!%dI" % (4 * order_book.TOP_LEVEL_COUNT))  # Prices & volumes for best bids & asks

# Helpers for decoding order book and trade ticks messages
BOOK_PART = struct.Struct("!%dI" % order_book.TOP_LEVEL_COUNT)
TICKS_PART = struct.Struct("!%dI" % order_book.TOP_LEVEL_COUNT)

# Matching engine to HUD messages
AMEND_EVENT_MESSAGE = struct.Struct("!dIIi")  # Time, team id, order id, volume delta
CANCEL_EVENT_MESSAGE = struct.Struct("!dII")  # Time, team id, order id
INSERT_EVENT_MESSAGE = struct.Struct("!dIIBBIIB")  # Time, team id, order id, inst, side, volume, price, lifespan
LOGIN_EVENT_MESSAGE = struct.Struct("!50sI")  # Team name, team id
HEDGE_EVENT_MESSAGE = struct.Struct("!dIBBId")  # Time, team id, side, instrument, volume, price
TRADE_EVENT_MESSAGE = struct.Struct("!dIIBBIIi")  # Time, team id, order id, side, instrument, volume, price, fee

# Cumulative message sizes
HEADER_SIZE: int = HEADER.size

AMEND_MESSAGE_SIZE: int = HEADER.size + AMEND_MESSAGE.size
CANCEL_MESSAGE_SIZE: int = HEADER.size + CANCEL_MESSAGE.size
HEDGE_MESSAGE_SIZE: int = HEADER.size + HEDGE_MESSAGE.size
INSERT_MESSAGE_SIZE: int = HEADER.size + INSERT_MESSAGE.size
LOGIN_MESSAGE_SIZE: int = HEADER.size + LOGIN_MESSAGE.size

ERROR_MESSAGE_SIZE: int = HEADER.size + ERROR_MESSAGE.size
HEDGE_FILLED_MESSAGE_SIZE: int = HEADER.size + HEDGE_FILLED_MESSAGE.size
ORDER_BOOK_HEADER_SIZE: int = HEADER.size + ORDER_BOOK_HEADER.size
ORDER_BOOK_MESSAGE_SIZE: int = ORDER_BOOK_HEADER_SIZE + ORDER_BOOK_MESSAGE.size
ORDER_FILLED_MESSAGE_SIZE: int = HEADER.size + ORDER_FILLED_MESSAGE.size
ORDER_STATUS_MESSAGE_SIZE: int = HEADER.size + ORDER_STATUS_MESSAGE.size
TRADE_TICKS_HEADER_SIZE: int = HEADER.size + TRADE_TICKS_HEADER.size
TRADE_TICKS_MESSAGE_SIZE: int = TRADE_TICKS_HEADER_SIZE + TRADE_TICKS_MESSAGE.size

AMEND_EVENT_MESSAGE_SIZE: int = HEADER.size + AMEND_EVENT_MESSAGE.size
CANCEL_EVENT_MESSAGE_SIZE: int = HEADER.size + CANCEL_EVENT_MESSAGE.size
INSERT_EVENT_MESSAGE_SIZE: int = HEADER.size + INSERT_EVENT_MESSAGE.size
HEDGE_EVENT_MESSAGE_SIZE: int = HEADER.size + HEDGE_EVENT_MESSAGE.size
TRADE_EVENT_MESSAGE_SIZE: int = HEADER.size + TRADE_EVENT_MESSAGE.size
LOGIN_EVENT_MESSAGE_SIZE: int = HEADER.size + LOGIN_EVENT_MESSAGE.size


class Connection(asyncio.Protocol):
    """A stream-based network connection."""

    def __init__(self):
        """Initialize a new instance of the Connection class."""
        self._closing: bool = False
        self._data: bytes = b""
        self._file_number: int = 0
        self._connection_transport: Optional[asyncio.Transport] = None

        self.__logger = logging.getLogger("CONNECTION")

    def close(self):
        """Close the connection."""
        self._closing = True
        if self._connection_transport is not None and not self._connection_transport.is_closing():
            self._connection_transport.close()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Callback when a connection has been lost."""
        if exc is not None:
            self.__logger.error("fd=%d connection lost:", self._file_number, exc_info=exc)
        else:
            self.__logger.info("fd=%d connection lost", self._file_number)
        self._connection_transport = None

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        """Callback when a connection has been established."""
        sock = transport.get_extra_info("socket")
        if sock is not None:
            self._file_number = sock.fileno()
        self.__logger.info("fd=%d connection established: peer=%s:%d", self._file_number,
                           *(transport.get_extra_info("peername") or ("unknown", 0)))
        self._connection_transport = transport

    def data_received(self, data: bytes) -> None:
        """Called when data is received."""
        if self._data:
            self._data += data
        else:
            self._data = data

        upto: int = 0
        data_length: int = len(self._data)

        while not self._closing and upto < data_length - HEADER_SIZE:
            length, typ = HEADER.unpack_from(self._data, upto)
            if upto + length > data_length:
                break

            self.on_message(typ, self._data, upto + HEADER_SIZE, length)

            upto += length

        self._data = self._data[upto:]

    def on_message(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Callback when an individual message has been received."""

    def send_message(self, typ: int, data: bytes, length: int) -> None:
        """Send a message."""
        self._connection_transport.write(HEADER.pack(length, typ) + data)


class Subscription(asyncio.DatagramProtocol):
    """A packet-based network receiver."""

    def __init__(self):
        """Initialise a new instance of the Receiver class."""
        self._receiver_transport: Optional[asyncio.BaseTransport] = None
        self.__logger = logging.getLogger("RECEIVER")

    def close(self):
        """Close the subscription."""
        self._receiver_transport.close()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Callback when the datagram receiver has lost its connection."""
        if exc is not None:
            self.__logger.error("connection lost:", exc_info=exc)
        else:
            self.__logger.info("connection lost")
        self._receiver_transport = None

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        """Callback when the datagram receiver is established."""
        self._receiver_transport = transport

    def datagram_received(self, data: bytes, address: Tuple[str, int]) -> None:
        """Callback when a datagram is received."""
        if len(data) < HEADER_SIZE:
            self.__logger.warning("ignoring malformed datagram from %s:%d length=%d", *address, len(data))
            return

        length, typ = HEADER.unpack_from(data)
        if length != len(data):
            self.__logger.warning("ignoring malformed datagram from %s:%d expected_length=%d actual_length=%d",
                                  *address, length, len(data))
            return

        self.on_datagram(typ, data, HEADER_SIZE, length)

    def on_datagram(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Callback when a datagram is received."""
