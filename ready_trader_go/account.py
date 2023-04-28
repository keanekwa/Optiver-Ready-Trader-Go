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
from .types import Instrument, Side


class CompetitorAccount(object):
    """A competitors account."""

    def __init__(self, tick_size: float, etf_clamp: float):
        """Initialise a new instance of the CompetitorAccount class."""
        self.account_balance: int = 0
        self.buy_volume: int = 0
        self.etf_clamp: float = etf_clamp
        self.etf_position: int = 0
        self.future_position: int = 0
        self.max_drawdown: int = 0
        self.max_profit: int = 0
        self.profit_or_loss: int = 0
        self.sell_volume: int = 0
        self.tick_size: int = int(tick_size * 100.0)
        self.total_fees: int = 0

    def transact(self, instrument: Instrument, side: Side, price: float, volume: int, fee: int) -> None:
        """Update this account with the specified transaction."""
        if side == Side.SELL:
            self.account_balance += round(price * volume)
        else:
            self.account_balance -= round(price * volume)

        self.account_balance -= fee
        self.total_fees += fee

        if instrument == Instrument.FUTURE:
            if side == Side.SELL:
                self.future_position -= volume
            else:
                self.future_position += volume
        else:
            if side == Side.SELL:
                self.sell_volume += volume
                self.etf_position -= volume
            else:
                self.buy_volume += volume
                self.etf_position += volume

    def update(self, future_price: int, etf_price: int) -> None:
        """Update this account using the specified prices."""
        delta: int = round(self.etf_clamp * future_price)
        delta -= delta % self.tick_size
        min_price: int = future_price - delta
        max_price: int = future_price + delta
        clamped: int = min_price if etf_price < min_price else max_price if etf_price > max_price else etf_price
        self.profit_or_loss = self.account_balance + self.future_position * future_price + self.etf_position * clamped
        if self.profit_or_loss > self.max_profit:
            self.max_profit = self.profit_or_loss
        if self.max_profit - self.profit_or_loss > self.max_drawdown:
            self.max_drawdown = self.max_profit - self.profit_or_loss


class AccountFactory:
    """A factory class for CompetitorAccounts."""

    def __init__(self, etf_clamp: float, tick_size: float):
        """Initialise a new instance of the AccountFactory class."""
        self.etf_clamp: float = etf_clamp
        self.tick_size: float = tick_size

    def create(self) -> CompetitorAccount:
        """Return a new instance of the CompetitorAccount class."""
        return CompetitorAccount(self.tick_size, self.etf_clamp)
