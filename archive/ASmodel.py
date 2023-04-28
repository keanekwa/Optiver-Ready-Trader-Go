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
import itertools

from typing import List
import math
import numpy as np
from scipy.stats import linregress

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side


LOT_SIZE = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS


class AutoTrader(BaseAutoTrader):
    """Example Auto-trader.

    When it starts this auto-trader places ten-lot bid and ask orders at the
    current best-bid and best-ask prices respectively. Thereafter, if it has
    a long position (it has bought more lots than it has sold) it reduces its
    bid and ask prices. Conversely, if it has a short position (it has sold
    more lots than it has bought) then it increases its bid and ask prices.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0

        self.mid_prices = []
        self.T = 1 # Reserve pricing time
        self.bid_prices = np.array([])
        self.ask_prices = np.array([])

        self.bid_volume = []
        self.ask_volume = []

        self.BID_LOT_SIZE = 10
        self.ASK_LOT_SIZE = 10
        self.steps = 0


    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received hedge filled for order %d with average price %d and volume %d", client_order_id,
                         price, volume)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        self.logger.info("received order book for instrument %d with sequence number %d", instrument,
                         sequence_number)


        if instrument == Instrument.FUTURE and len(bid_prices) > 0 and len(ask_prices) > 0 and bid_prices[0] > 0 and ask_prices[0] > 0:
            """
            s - mid market price
            q - difference between current size and counterparty order size
            gamma - sensitivity parameter (how much our quote should move in response to inventory changes)
            var - price variance (calculated using mid price over x rolling window)
            T - time difference but ill ignore that first
            k - order book liquidity density
            r - reservation price
            delta - optimal spread // 2
            """
            
            s = (bid_prices[0] + ask_prices[0]) / (2 * TICK_SIZE_IN_CENTS) # mid price in $
            q = 0
            gamma = 0.1 # TODO: Optimise this
            var = 0
            k = 1 # TODO: Assuming constant liquidity
            if self.T > 0:
                self.T -= 0.002 # TODO: Try to find appropriate T - t
            else:
                self.T = 0.000001

            if int(s) != 0:
                self.mid_prices.append(s)

            lookback = 10

            if len(self.mid_prices) >= lookback:
                var = np.var(self.mid_prices[-1:-lookback - 1:-1])  # not sure to include current mid price
                q = self.position
                # TODO: Better way to find K
                """
                K using changing prices / timesteps
                k = (len(set(self.bid_prices[-1:-lookback-1:-1]))) / lookback
                """

                """               
                # K using current spread THIS IS GIVING MATH DOMAIN ERROR
                spread_lookback = 10
                spread = self.ask_prices[-spread_lookback:] - self.bid_prices[-spread_lookback:]
                print(spread)
                time_index = np.array(range(spread_lookback))
                model = linregress(time_index, spread)
                k = 1 / model.slope
                """

                # TODO: Momentum LOTSIZE -- Try to properly model lotsize
                """
                if sum(self.bid_volume[-1:-lookback - 1:-1]) > sum(self.ask_volume[-1:-lookback - 1:-1]):
                    self.BID_LOT_SIZE = math.ceil(LOT_SIZE + 5)
                    self.ASK_LOT_SIZE = math.ceil(LOT_SIZE - 5)
                else:
                    self.ASK_LOT_SIZE = math.ceil(LOT_SIZE + 5)
                    self.BID_LOT_SIZE = math.ceil(LOT_SIZE - 5)
                """

            # Reserve pricing
            r = s - (q * gamma * var * self.T)

            # TODO: Find K properly (order book liqudity)
            delta = (gamma * var * self.T + (2 / gamma * math.log(1 + (gamma / k))))

            # Prices to be sent in
            new_bid_price = math.ceil((r - delta / 2)) * TICK_SIZE_IN_CENTS
            new_ask_price = math.ceil((r + delta / 2)) * TICK_SIZE_IN_CENTS

            if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
            if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0

            if self.bid_id == 0 and new_bid_price != 0 and self.position <= POSITION_LIMIT - (LOT_SIZE * len(self.bids) + LOT_SIZE):
                self.bid_id = next(self.order_ids)
                self.bid_price = new_bid_price
                self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, self.BID_LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.bid_id)

            if self.ask_id == 0 and new_ask_price != 0 and self.position >= -POSITION_LIMIT + (LOT_SIZE * len(self.asks) + LOT_SIZE):
                self.ask_id = next(self.order_ids)
                self.ask_price = new_ask_price
                self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, self.ASK_LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.ask_id)

            # Add volume at the end and prices after sending order
            self.bid_volume.append(sum(bid_volumes))
            self.ask_volume.append(sum(ask_volumes))
            self.ask_prices = np.append(self.ask_prices, ask_prices[0])
            self.bid_prices = np.append(self.bid_prices, bid_prices[0])

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.bids:
            self.position += volume
            self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
        elif client_order_id in self.asks:
            self.position -= volume
            self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
                         client_order_id, fill_volume, remaining_volume, fees)

        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0

            # It could be either a bid or an ask
            self.bids.discard(client_order_id)
            self.asks.discard(client_order_id)

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the aggregated volume
        traded at each of those price levels.

        If there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes arrays.
        """
        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
                         sequence_number)
