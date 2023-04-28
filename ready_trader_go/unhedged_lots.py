import asyncio

from typing import Any, Callable, Optional

MAX_UNHEDGED_LOTS: int = 10
UNHEDGED_LOTS_TIME_LIMIT: int = 60


class UnhedgedLots:
    """Keep track of unhedged lots and call a callback if unhedged lots are held for too long."""

    def __init__(self, callback: Callable[[], Any]):
        """Initialise a new instance of the UnhedgedLots class."""
        self.callback: Callable[[], None] = callback
        self.relative_position: int = 0
        self.timer_handle: Optional[asyncio.TimerHandle] = None

    @property
    def unhedged_lot_count(self) -> int:
        """Return the number of unhedged lots."""
        if self.relative_position > MAX_UNHEDGED_LOTS:
            return self.relative_position - MAX_UNHEDGED_LOTS
        elif self.relative_position < -MAX_UNHEDGED_LOTS:
            return self.relative_position + MAX_UNHEDGED_LOTS
        return 0

    def apply_position_delta(self, delta: int) -> None:
        """Apply the given position delta to this unhedged lots instance."""
        new_relative_position: int = self.relative_position + delta

        if delta > 0:
            if self.relative_position < -MAX_UNHEDGED_LOTS <= new_relative_position:
                self.timer_handle.cancel()

            if new_relative_position > MAX_UNHEDGED_LOTS >= self.relative_position:
                self.timer_handle = asyncio.get_running_loop().call_later(UNHEDGED_LOTS_TIME_LIMIT, self.callback)
        elif delta < 0:
            if self.relative_position > MAX_UNHEDGED_LOTS >= new_relative_position:
                self.timer_handle.cancel()

            if new_relative_position < -MAX_UNHEDGED_LOTS <= self.relative_position:
                self.timer_handle = asyncio.get_running_loop().call_later(UNHEDGED_LOTS_TIME_LIMIT, self.callback)

        self.relative_position = new_relative_position


class UnhedgedLotsFactory:
    """A factory class for UnhedgedLots instances."""

    def __init__(self):
        """Initialise a new instance of the UnhedgedLotsFactory class."""

    def create(self, callback: Callable[[], Any]) -> UnhedgedLots:
        """Return a new instance of the UnhedgedLots class."""
        return UnhedgedLots(callback)
