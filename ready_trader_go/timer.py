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
import time
import random

from typing import Any, Callable, List, Optional


class Timer:
    """A timer."""

    def __init__(self, tick_interval: float, speed: float):
        """Initialise a new instance of the timer class."""
        self.__event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.__logger: logging.Logger = logging.getLogger("TIMER")
        self.__speed: float = speed
        self.__start_time: float = 0.0
        self.__tick_timer_handle: Optional[asyncio.TimerHandle] = None
        self.__tick_interval: float = tick_interval

        # Signals
        self.timer_started: List[Callable[[Any, float], None]] = list()
        self.timer_stopped: List[Callable[[Any, float], None]] = list()
        self.timer_ticked: List[Callable[[Any, float, int], None]] = list()

    def advance(self) -> float:
        """Advance the timer."""
        if self.__start_time:
            now = (time.monotonic() - self.__start_time) * self.__speed
            return now
        return 0.0

    def __on_timer_tick(self, tick_time: float, tick_number: int):
        """Called on each timer tick."""
        now = (time.monotonic() - self.__start_time) * self.__speed

        # There may have been a delay, so work out which tick this really is
        # We also need to prevent "skipping" ticks backwards due to negative random jitter
        skipped_ticks: float = max(0, (now - tick_time) // self.__tick_interval)
        if skipped_ticks:
            tick_time += self.__tick_interval * skipped_ticks
            tick_number += int(skipped_ticks)

        for callback in self.timer_ticked:
            callback(self, now, tick_number)

        tick_time += self.__tick_interval

        # Generate random jitter, which can be +/- 20% of standard tick interval
        limit = self.__tick_interval * 0.2
        jitter = random.uniform(-limit, +limit) / self.__speed

        self.__tick_timer_handle = self.__event_loop.call_at(self.__start_time + jitter + tick_time/self.__speed,
                                                             self.__on_timer_tick, tick_time, tick_number + 1)

    def start(self) -> None:
        """Start this timer."""
        self.__event_loop = asyncio.get_running_loop()
        self.__start_time = time.monotonic()
        for callback in self.timer_started:
            callback(self, self.__start_time)
        self.__on_timer_tick(0.0, 1)

    def shutdown(self, now: float, reason: str) -> None:
        """Shut down this timer."""
        self.__logger.info("shutting down the match: time=%.6f reason='%s'", now, reason)
        if self.__tick_timer_handle:
            self.__tick_timer_handle.cancel()
        for callback in self.timer_stopped:
            callback(self, now)
