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

from typing import Optional

from .competitor import Competitor, CompetitorManager
from .limiter import FrequencyLimiter, FrequencyLimiterFactory
from .messages import (AMEND_MESSAGE, AMEND_MESSAGE_SIZE, CANCEL_MESSAGE, CANCEL_MESSAGE_SIZE,
                       ERROR_MESSAGE, ERROR_MESSAGE_SIZE, HEADER, HEADER_SIZE, HEDGE_FILLED_MESSAGE,
                       HEDGE_FILLED_MESSAGE_SIZE, HEDGE_MESSAGE, HEDGE_MESSAGE_SIZE, INSERT_MESSAGE,
                       INSERT_MESSAGE_SIZE, LOGIN_MESSAGE, LOGIN_MESSAGE_SIZE, ORDER_FILLED_MESSAGE,
                       ORDER_FILLED_MESSAGE_SIZE, ORDER_STATUS_MESSAGE, ORDER_STATUS_MESSAGE_SIZE,
                       Connection, MessageType)
from .types import IController, IExecutionConnection


class ExecutionConnection(Connection, IExecutionConnection):
    def __init__(self, competitor_manager: CompetitorManager, frequency_limiter: FrequencyLimiter,
                 controller: IController):
        """Initialise a new instance of the ExecutionChannel class."""
        Connection.__init__(self)

        self.competitor: Optional[Competitor] = None
        self.competitor_manager: CompetitorManager = competitor_manager
        self.controller: IController = controller
        self.closing: bool = False
        self.frequency_limiter: FrequencyLimiter = frequency_limiter
        self.logger: logging.Logger = logging.getLogger("EXECUTION")
        self.login_timeout: asyncio.Handle = asyncio.get_running_loop().call_later(1.0, self.close)

        self.__error_message = bytearray(ERROR_MESSAGE_SIZE)
        self.__hedge_filled_message = bytearray(HEDGE_FILLED_MESSAGE_SIZE)
        self.__order_status_message = bytearray(ORDER_STATUS_MESSAGE_SIZE)
        self.__order_filled_message = bytearray(ORDER_FILLED_MESSAGE_SIZE)

        HEADER.pack_into(self.__error_message, 0, ERROR_MESSAGE_SIZE, MessageType.ERROR)
        HEADER.pack_into(self.__hedge_filled_message, 0, HEDGE_FILLED_MESSAGE_SIZE, MessageType.HEDGE_FILLED)
        HEADER.pack_into(self.__order_status_message, 0, ORDER_STATUS_MESSAGE_SIZE, MessageType.ORDER_STATUS)
        HEADER.pack_into(self.__order_filled_message, 0, ORDER_FILLED_MESSAGE_SIZE, MessageType.ORDER_FILLED)

    def __del__(self):
        """Clean up this instance of the ExecutionChannel class."""
        self.login_timeout.cancel()

    def close(self):
        """Close the connection associated with this ExecutionChannel instance."""
        Connection.close(self)
        self.login_timeout.cancel()
        self.closing = True
        if self._connection_transport and not self._connection_transport.is_closing():
            self._connection_transport.close()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when the connection to the auto-trader is lost."""
        Connection.connection_lost(self, exc)

        self.login_timeout.cancel()
        if self.competitor is not None:
            self.competitor.on_connection_lost(self.controller.advance_time())
        self.competitor_manager.on_competitor_disconnect()
        if not self.closing:
            self.logger.warning("fd=%d lost connection to auto-trader:", self._file_number, exc_info=exc)

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        """Called when the connection is established."""
        Connection.connection_made(self, transport)
        self.competitor_manager.on_competitor_connect()

    def on_message(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Called when a message is received from the auto-trader."""
        now: float = self.controller.advance_time()

        if self.frequency_limiter.check_event(now):
            self.logger.info("fd=%d message frequency limit breached: now=%.6f value=%d limit=%d",
                             self._file_number, now, self.frequency_limiter.value, self.frequency_limiter.limit)
            if self.competitor is not None:
                self.competitor.hard_breach(now, 0, b"message frequency limit breached")
            else:
                self.close()
            return

        if self.competitor is None:
            if typ == MessageType.LOGIN and length == LOGIN_MESSAGE_SIZE:
                raw_name, raw_secret = LOGIN_MESSAGE.unpack_from(data, start)
                self.on_login(raw_name.rstrip(b"\x00").decode(), raw_secret.rstrip(b"\x00").decode())
            else:
                self.logger.info("fd=%d first message received was not a login", self._file_number)
                self.close()
            return

        if typ == MessageType.AMEND_ORDER and length == AMEND_MESSAGE_SIZE:
            self.competitor.on_amend_message(now, *AMEND_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.CANCEL_ORDER and length == CANCEL_MESSAGE_SIZE:
            self.competitor.on_cancel_message(now, *CANCEL_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.HEDGE_ORDER and length == HEDGE_MESSAGE_SIZE:
            self.competitor.on_hedge_message(now, *HEDGE_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.INSERT_ORDER and length == INSERT_MESSAGE_SIZE:
            self.competitor.on_insert_message(now, *INSERT_MESSAGE.unpack_from(data, start))
        else:
            if typ == MessageType.LOGIN:
                self.logger.info("fd=%d received second login message: time=%.6f name='%s'", self._file_number,
                                 now, self.competitor.name)
            else:
                self.logger.info("fd=%d '%s' received invalid message: time=%.6f length=%d type=%d",
                                 self._file_number, self.competitor.name, now, length, typ)
            self.close()

    def on_login(self, name: str, secret: str) -> None:
        """Called when a login message is received."""
        self.login_timeout.cancel()

        self.competitor = self.competitor_manager.login_competitor(name, secret, self)
        if self.competitor is None:
            self.logger.info("fd=%d login failed: name='%s'", self._file_number, name)
            self.close()
            return

        self.logger.info("fd=%d '%s' is ready!", self._file_number, name)

    def send_error(self, client_order_id: int, error_message: bytes) -> None:
        """Send an error message to the auto-trader."""
        ERROR_MESSAGE.pack_into(self.__error_message, HEADER_SIZE, client_order_id, error_message)
        self._connection_transport.write(self.__error_message)

    def send_hedge_filled(self, client_order_id: int, average_price: int, volume: int) -> None:
        """Send a hedge filled message to the auto-trader."""
        HEDGE_FILLED_MESSAGE.pack_into(self.__hedge_filled_message, HEADER_SIZE, client_order_id, average_price,
                                       volume)
        self._connection_transport.write(self.__hedge_filled_message)

    def send_order_filled(self, client_order_id: int, price: int, volume: int) -> None:
        """Send an order filled message to the auto-trader."""
        ORDER_FILLED_MESSAGE.pack_into(self.__order_filled_message, HEADER_SIZE, client_order_id, price, volume)
        self._connection_transport.write(self.__order_filled_message)

    def send_order_status(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Send an order status message to the auto-trader."""
        ORDER_STATUS_MESSAGE.pack_into(self.__order_status_message, HEADER_SIZE, client_order_id, fill_volume,
                                       remaining_volume, fees)
        self._connection_transport.write(self.__order_status_message)


class ExecutionServer:
    """A server for execution connections."""
    def __init__(self, host: str, port: int, competitor_manager: CompetitorManager,
                 limiter_factory: FrequencyLimiterFactory):
        """Initialise a new instance of the ExecutionServer class."""
        self.controller: Optional[IController] = None
        self.host: str = host
        self.port: int = port

        self.__competitor_manager: CompetitorManager = competitor_manager
        self.__limiter_factory: FrequencyLimiterFactory = limiter_factory
        self.__logger = logging.getLogger("EXECUTION")
        self.__server: Optional[asyncio.AbstractServer] = None

    def close(self):
        """Close the server without affecting existing connections."""
        self.__server.close()

    def __on_new_connection(self) -> ExecutionConnection:
        """Callback for when a new connection is accepted."""
        return ExecutionConnection(self.__competitor_manager, self.__limiter_factory.create(), self.controller)

    async def start(self) -> None:
        """Start the server."""
        self.__logger.info("starting execution server: host=%s port=%d", self.host, self.port)
        self.__server = await asyncio.get_running_loop().create_server(self.__on_new_connection, self.host, self.port)
