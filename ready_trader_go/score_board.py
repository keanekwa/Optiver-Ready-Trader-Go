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
import csv
import logging
import queue
import threading

from typing import Callable, List, Optional, TextIO

from .account import CompetitorAccount


class ScoreRecord:
    __slots__ = ("time", "team", "operation", "buy_volume", "sell_volume", "etf_position", "future_position",
                 "etf_price", "future_price", "total_fees", "balance", "profit_loss", "status")

    def __init__(self, time: float, team: str, operation: str, buy_volume: int, sell_volume: int, etf_position: int,
                 future_position, etf_price: Optional[int], future_price: Optional[int], total_fees: int, balance: int,
                 profit_loss: int, status: Optional[str] = None):
        self.time: float = time
        self.team: str = team
        self.operation: str = operation
        self.buy_volume: int = buy_volume
        self.sell_volume: int = sell_volume
        self.etf_position: int = etf_position
        self.future_position: int = future_position
        self.etf_price: int = etf_price
        self.future_price: int = future_price
        self.total_fees: int = total_fees
        self.balance: int = balance
        self.profit_loss: int = profit_loss
        self.status: str = status

    def __iter__(self):
        return iter((round(self.time, 6),
                     self.team,
                     self.operation,
                     self.buy_volume,
                     self.sell_volume,
                     self.etf_position,
                     self.future_position,
                     self.etf_price if self.etf_price is not None else None,
                     self.future_price if self.future_price is not None else None,
                     round(self.total_fees, 2),
                     round(self.balance, 2),
                     round(self.profit_loss, 2),
                     self.status))


class ScoreBoardWriter:
    """A processor of score records that it writes to a file."""

    def __init__(self, filename: str, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the MatchEvents class."""
        self.event_loop: asyncio.AbstractEventLoop = loop
        self.filename: str = filename
        self.finished: bool = False
        self.logger = logging.getLogger("SCORE_BOARD")
        self.queue: queue.Queue = queue.Queue()
        self.writer_task: Optional[threading.Thread] = None

        self.task_complete: List[Callable] = list()

    def __del__(self):
        """Destroy an instance of the MatchEvents class."""
        if not self.finished:
            self.queue.put(None)
        self.writer_task.join()

    def breach(self, now: float, name: str, account: CompetitorAccount, etf_price: Optional[int],
               future_price: Optional[int]) -> None:
        """Create a new disconnect event."""
        self.queue.put(
            ScoreRecord(now, name, "Breach", account.buy_volume, account.sell_volume, account.etf_position,
                        account.future_position, etf_price, future_price, account.total_fees, account.account_balance,
                        account.profit_or_loss))

    def disconnect(self, now: float, name: str, account: CompetitorAccount, etf_price: Optional[int],
                   future_price: Optional[int]) -> None:
        """Create a new disconnect event."""
        if not self.finished:
            self.queue.put(
                ScoreRecord(now, name, "Disconnect", account.buy_volume, account.sell_volume, account.etf_position,
                            account.future_position, etf_price, future_price, account.total_fees,
                            account.account_balance, account.profit_or_loss))

    def finish(self) -> None:
        """Indicate the the series of events is complete."""
        self.queue.put(None)
        self.finished = True

    def on_writer_done(self, num_events: int) -> None:
        """Called when the match event writer thread is done."""
        for c in self.task_complete:
            c(self)
        self.logger.info("writer thread complete after processing %d score records", num_events)

    def start(self):
        """Start the score board writer thread"""
        try:
            score_board = open(self.filename, "w", newline="")
        except IOError as e:
            self.logger.error("failed to open score board file: filename=%s", self.filename, exc_info=e)
            raise
        else:
            self.writer_task = threading.Thread(target=self.writer, args=(score_board,), daemon=False,
                                                name="score_board")
            self.writer_task.start()

    def tick(self, now: float, name: str, account: CompetitorAccount, etf_price: Optional[int],
             future_price: Optional[int], status: Optional[str] = None) -> None:
        """Create a new tick event"""
        self.queue.put(
            ScoreRecord(now, name, "Tick", account.buy_volume, account.sell_volume, account.etf_position,
                        account.future_position, etf_price, future_price, account.total_fees, account.account_balance,
                        account.profit_or_loss, status))

    def writer(self, score_records_file: TextIO) -> None:
        """Fetch score records from a queue and write them to a file"""
        count = 0
        fifo = self.queue

        try:
            with score_records_file:
                csv_writer = csv.writer(score_records_file)
                csv_writer.writerow(("Time,Team,Operation,BuyVolume,SellVolume,EtfPosition,FuturePosition,"
                                     "EtfPrice,FuturePrice,TotalFees,AccountBalance,ProfitOrLoss,"
                                     "Status").split(','))

                evt = fifo.get()
                while evt is not None:
                    count += 1
                    csv_writer.writerow(evt)
                    evt = fifo.get()
        finally:
            if not self.event_loop.is_closed():
                self.event_loop.call_soon_threadsafe(self.on_writer_done, count)
