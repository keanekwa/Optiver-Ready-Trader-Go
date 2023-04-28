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

from typing import Any, Optional

from .execution import ExecutionServer
from .heads_up import HeadsUpDisplayServer
from .information import InformationPublisher
from .market_events import MarketEventsReader
from .match_events import MatchEventsWriter
from .score_board import ScoreBoardWriter
from .timer import Timer
from .types import IController


class Controller(IController):
    """Controller for the Ready Trader Go matching engine."""

    def __init__(self, market_open_delay: float, exec_server: ExecutionServer, info_publisher: InformationPublisher,
                 market_events_reader: MarketEventsReader, match_events_writer: MatchEventsWriter,
                 score_board_writer: ScoreBoardWriter, market_timer: Timer, tick_timer: Timer):
        """Initialise a new instance of the Controller class."""
        self.heads_up_display_server: Optional[HeadsUpDisplayServer] = None

        self.__done: bool = False
        self.__execution_server: ExecutionServer = exec_server
        self.__information_publisher: InformationPublisher = info_publisher
        self.__logger: logging.Logger = logging.getLogger("CONTROLLER")
        self.__market_events_reader = market_events_reader
        self.__market_open_delay: float = market_open_delay
        self.__market_timer: Timer = market_timer
        self.__match_events_writer = match_events_writer
        self.__score_board_writer = score_board_writer
        self.__tick_timer: Timer = tick_timer

        # Connect signals
        self.__match_events_writer.task_complete.append(self.on_task_complete)
        self.__market_events_reader.task_complete.append(self.on_task_complete)
        self.__market_timer.timer_ticked.append(self.on_market_timer_ticked)
        self.__score_board_writer.task_complete.append(self.on_task_complete)
        self.__tick_timer.timer_stopped.append(self.on_tick_timer_stopped)
        self.__tick_timer.timer_ticked.append(self.on_tick_timer_ticked)

    def advance_time(self):
        """Return the current time after accounting for events."""
        now: float = self.__market_timer.advance()
        self.__market_events_reader.process_market_events(now)
        return now

    def cleanup(self) -> None:
        """Ensure the controller shuts down gracefully"""
        if self.__match_events_writer:
            self.__match_events_writer.finish()

        if self.__score_board_writer:
            self.__score_board_writer.finish()

    def on_market_timer_ticked(self, timer: Timer, now: float, _: int):
        """Called when it is time to process market events."""
        self.__market_events_reader.process_market_events(now)

    def on_task_complete(self, task: Any) -> None:
        """Called when a reader or writer task is complete"""
        if task is self.__match_events_writer:
            self.__match_events_writer = None
        elif task is self.__score_board_writer:
            self.__score_board_writer = None
        elif task is self.__market_events_reader:
            self.__done = True

        if self.__match_events_writer is None and self.__score_board_writer is None:
            asyncio.get_running_loop().stop()

    def on_tick_timer_stopped(self, timer: Timer, now: float) -> None:
        """Shut down the match."""
        self.__match_events_writer.finish()
        self.__score_board_writer.finish()

    def on_tick_timer_ticked(self, timer: Timer, now: float, _: int) -> None:
        """Called when it is time to send an order book update and trade ticks."""
        if self.__done:
            timer.shutdown(now, "match complete")
            return

    async def start(self) -> None:
        """Start running the match."""
        self.__logger.info("starting the match")

        await self.__execution_server.start()
        await self.__information_publisher.start()
        if self.heads_up_display_server:
            await self.heads_up_display_server.start()

        self.__market_events_reader.start()
        self.__match_events_writer.start()
        self.__score_board_writer.start()

        # Give the auto-traders time to start up and connect
        await asyncio.sleep(self.__market_open_delay)
        # self.__execution_server.close()

        self.__logger.info("market open")
        self.__market_timer.start()
        self.__tick_timer.start()
