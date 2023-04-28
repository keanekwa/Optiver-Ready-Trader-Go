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
import sys

from typing import Deque


class FrequencyLimiter(object):
    """Limit the frequency of events in a specified time interval."""

    def __init__(self, interval: float, limit: int):
        """Initialise a new instance of the FrequencyLimiter class."""
        self.events: Deque[float] = collections.deque()
        self.interval: float = interval
        self.limit: int = limit
        self.value: int = 0

    def check_event(self, now: float) -> bool:
        """Return True if the new event breaches the limit, False otherwise.

        This method should be called with a monotonically increasing sequence
        of times.
        """
        self.value += 1
        self.events.append(now)

        epsilon: float = sys.float_info.epsilon
        first: float = self.events[0]
        window_start: float = now - self.interval

        while (first - window_start) <= ((first if first > window_start else window_start) * epsilon):
            self.events.popleft()
            self.value -= 1
            first = self.events[0]

        return self.value > self.limit


class FrequencyLimiterFactory:
    """A factory class for FrequencyLimiters."""

    def __init__(self, interval: float, limit: int):
        """Initialise a new instance of the FrequencyLimiterFactory class."""
        self.frequency_limit_interval: float = interval
        self.frequency_limit: int = limit

    def create(self) -> FrequencyLimiter:
        """Return a new FrequencyLimiter instance."""
        return FrequencyLimiter(self.frequency_limit_interval, self.frequency_limit)
