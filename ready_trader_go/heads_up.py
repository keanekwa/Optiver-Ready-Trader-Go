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

from typing import Dict, Optional

from .competitor import CompetitorManager
from .match_events import MatchEvent, MatchEventOperation, MatchEvents
from .messages import (AMEND_MESSAGE, AMEND_MESSAGE_SIZE, CANCEL_MESSAGE, CANCEL_MESSAGE_SIZE,
                       ERROR_MESSAGE, ERROR_MESSAGE_SIZE, HEADER, HEADER_SIZE, INSERT_MESSAGE,
                       INSERT_MESSAGE_SIZE, LOGIN_MESSAGE, LOGIN_MESSAGE_SIZE,
                       AMEND_EVENT_MESSAGE, AMEND_EVENT_MESSAGE_SIZE, CANCEL_EVENT_MESSAGE, CANCEL_EVENT_MESSAGE_SIZE,
                       INSERT_EVENT_MESSAGE, INSERT_EVENT_MESSAGE_SIZE, HEDGE_EVENT_MESSAGE, HEDGE_EVENT_MESSAGE_SIZE,
                       LOGIN_EVENT_MESSAGE, LOGIN_EVENT_MESSAGE_SIZE,
                       TRADE_EVENT_MESSAGE, TRADE_EVENT_MESSAGE_SIZE, Connection, MessageType)
from .types import ICompetitor, IController, IExecutionConnection


class HudConnection(Connection, IExecutionConnection):
    def __init__(self, match_events: MatchEvents, competitor_manager: CompetitorManager, controller: IController):
        """Initialise a new instance of the HudConnection class."""
        Connection.__init__(self)

        self.__competitor: Optional[ICompetitor] = None
        self.__competitor_ids: Dict[str, int] = {"": 0}
        self.__competitor_manager: CompetitorManager = competitor_manager
        self.__controller: IController = controller
        self.__logger = logging.getLogger("HEADS_UP")
        self.__match_events: MatchEvents = match_events

        # Message buffers
        self.__error_message = bytearray(ERROR_MESSAGE_SIZE)
        self.__amend_event_message = bytearray(AMEND_EVENT_MESSAGE_SIZE)
        self.__cancel_event_message = bytearray(CANCEL_EVENT_MESSAGE_SIZE)
        self.__insert_event_message = bytearray(INSERT_EVENT_MESSAGE_SIZE)
        self.__login_event_message = bytearray(LOGIN_EVENT_MESSAGE_SIZE)
        self.__hedge_event_message = bytearray(HEDGE_EVENT_MESSAGE_SIZE)
        self.__trade_event_message = bytearray(TRADE_EVENT_MESSAGE_SIZE)

        HEADER.pack_into(self.__error_message, 0, ERROR_MESSAGE_SIZE, MessageType.ERROR)
        HEADER.pack_into(self.__amend_event_message, 0, AMEND_EVENT_MESSAGE_SIZE, MessageType.AMEND_EVENT)
        HEADER.pack_into(self.__cancel_event_message, 0, CANCEL_EVENT_MESSAGE_SIZE, MessageType.CANCEL_EVENT)
        HEADER.pack_into(self.__insert_event_message, 0, INSERT_EVENT_MESSAGE_SIZE, MessageType.INSERT_EVENT)
        HEADER.pack_into(self.__login_event_message, 0, LOGIN_EVENT_MESSAGE_SIZE, MessageType.LOGIN_EVENT)
        HEADER.pack_into(self.__hedge_event_message, 0, HEDGE_EVENT_MESSAGE_SIZE, MessageType.HEDGE_EVENT)
        HEADER.pack_into(self.__trade_event_message, 0, TRADE_EVENT_MESSAGE_SIZE, MessageType.TRADE_EVENT)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when the connection to the heads-up display is lost."""
        Connection.connection_lost(self, exc)
        self.__match_events.event_occurred.remove(self.on_match_event)
        self.__competitor_manager.competitor_logged_in.remove(self.on_competitor_logged_in)
        self.__competitor_manager.on_competitor_disconnect()

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        """Called when a connection from a heads-up display is established."""
        Connection.connection_made(self, transport)
        self.__competitor_manager.on_competitor_connect()
        self.__competitor_manager.competitor_logged_in.append(self.on_competitor_logged_in)
        for competitor in self.__competitor_manager.get_competitors():
            self.on_competitor_logged_in(competitor.name)
        self.__match_events.event_occurred.append(self.on_match_event)

    def on_message(self, typ: int, data: bytes, start: int, length: int) -> None:
        """Callback when a message is received from the Heads-Up Display."""
        now: float = self.__controller.advance_time()

        if self.__competitor is None:
            if typ == MessageType.LOGIN and length == LOGIN_MESSAGE_SIZE:
                raw_name, raw_secret = LOGIN_MESSAGE.unpack_from(data, start)
                self.on_login(raw_name.rstrip(b"\x00").decode(), raw_secret.rstrip(b"\x00").decode())
            else:
                self.__logger.info("fd=%d first message received was not a login", self._file_number)
                self._connection_transport.close()
            return

        if typ == MessageType.AMEND_ORDER and length == AMEND_MESSAGE_SIZE:
            self.__competitor.on_amend_message(now, *AMEND_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.CANCEL_ORDER and length == CANCEL_MESSAGE_SIZE:
            self.__competitor.on_cancel_message(now, *CANCEL_MESSAGE.unpack_from(data, start))
        elif typ == MessageType.INSERT_ORDER and length == INSERT_MESSAGE_SIZE:
            self.__competitor.on_insert_message(now, *INSERT_MESSAGE.unpack_from(data, start))
        else:
            self.__logger.warning("fd=%d '%s' received invalid message: time=%.6f length=%d type=%d",
                                  self._file_number, length, typ)
            self.close()

    def on_competitor_logged_in(self, name: str) -> None:
        """Called when a competitor logs in."""
        identifier = self.__competitor_ids[name] = len(self.__competitor_ids) + 1
        LOGIN_EVENT_MESSAGE.pack_into(self.__login_event_message, HEADER_SIZE, name.encode(), identifier)
        self._connection_transport.write(self.__login_event_message)

    def on_login(self, name: str, secret: str) -> None:
        """Called when the heads-up display logs in."""
        self.__competitor = self.__competitor_manager.login_competitor(name, secret, self)

    def on_match_event(self, event: MatchEvent) -> None:
        """Called when a match event occurs."""
        if event.operation == MatchEventOperation.AMEND:
            AMEND_EVENT_MESSAGE.pack_into(self.__amend_event_message, HEADER_SIZE, event.time,
                                          self.__competitor_ids[event.competitor], event.order_id, event.volume)
            self._connection_transport.write(self.__amend_event_message)
        elif event.operation == MatchEventOperation.CANCEL:
            CANCEL_EVENT_MESSAGE.pack_into(self.__cancel_event_message, HEADER_SIZE, event.time,
                                           self.__competitor_ids[event.competitor], event.order_id)
            self._connection_transport.write(self.__cancel_event_message)
        elif event.operation == MatchEventOperation.INSERT:
            INSERT_EVENT_MESSAGE.pack_into(self.__insert_event_message, HEADER_SIZE, event.time,
                                           self.__competitor_ids[event.competitor], event.order_id,
                                           event.instrument.value, event.side.value, event.volume, event.price,
                                           event.lifespan.value)
            self._connection_transport.write(self.__insert_event_message)
        elif event.operation == MatchEventOperation.HEDGE:
            HEDGE_EVENT_MESSAGE.pack_into(self.__hedge_event_message, HEADER_SIZE, event.time,
                                          self.__competitor_ids[event.competitor], event.side, event.instrument,
                                          event.volume, event.price)
            self._connection_transport.write(self.__hedge_event_message)
        elif event.operation == MatchEventOperation.TRADE:
            TRADE_EVENT_MESSAGE.pack_into(self.__trade_event_message, HEADER_SIZE, event.time,
                                          self.__competitor_ids[event.competitor], event.order_id,
                                          event.side, event.instrument, event.volume, event.price, event.fee)
            self._connection_transport.write(self.__trade_event_message)

    # IExecutionConnection overrides

    def close(self):
        """Close the connection."""
        # Do nothing since the HUD should not be disconnected.

    def send_error(self, client_order_id: int, error_message: bytes) -> None:
        """Send an error message to the heads-up display."""
        ERROR_MESSAGE.pack_into(self.__error_message, HEADER_SIZE, client_order_id, error_message)
        self._connection_transport.write(self.__error_message)

    def send_order_filled(self, client_order_id: int, price: int, volume: int) -> None:
        """Send an order filled message to the heads-up display."""
        # Do nothing since the HUD will get a Trade event.

    def send_order_status(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Send an order status message to the heads-up display."""
        # Do nothing since the HUD will get Trade and cancel events.


class HeadsUpDisplayServer:
    def __init__(self, host: str, port: int, match_events: MatchEvents, competitor_manager: CompetitorManager,
                 controller: IController):
        """Initialise a new instance of the HeadsUpDisplayServer class."""
        self.host: str = host
        self.port: int = port

        self.__competitor_manager: CompetitorManager = competitor_manager
        self.__controller: IController = controller
        self.__logger: logging.Logger = logging.getLogger("HEADS_UP")
        self.__match_events: MatchEvents = match_events
        self.__server: Optional[asyncio.AbstractServer] = None

    def __on_new_connection(self):
        """Called when a new connection is established."""
        return HudConnection(self.__match_events, self.__competitor_manager, self.__controller)

    async def start(self):
        """Start this Heads Up Display server."""
        self.__logger.info("starting heads-up display server: host=%s port=%d", self.host, self.port)
        self.__server = await asyncio.get_running_loop().create_server(self.__on_new_connection, self.host, self.port)
