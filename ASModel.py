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
    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.hedge_bids = set()
        self.hedge_asks = set()
        self.hedge_position = 0

        self.mid_prices = []
        self.T = 1 # Reserve pricing time

        # Previous prices on Orderbook
        self.bid_prices = np.array([])
        self.ask_prices = np.array([])

        # At what price / volume our orders were filled
        self.orders_history = {"price": 0, "volume": 0}

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

        if len(bid_prices) == 0 or len(ask_prices) == 0 or bid_prices[0] == 0 or ask_prices[0] == 0:
            return

        if instrument == Instrument.FUTURE:
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
            gamma = 0.05
            var = 0
            k = 1
            if self.T > 0:
                self.T -= 0.002
            else:
                self.T = 0.000001

            if int(s) != 0:
                self.mid_prices.append(s)

            lookback = 10

            if len(self.mid_prices) >= lookback:
                var = np.var(self.mid_prices[-1:-lookback - 1:-1])
                q = self.position

            # Reservation pricing
            r = s - (q * gamma * var * self.T)

			# Bid ask spread
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
        elif client_order_id in self.asks:
            self.position -= volume
            volume = -volume

        # Record price and volume
        new_vol = self.orders_history["volume"] + volume

        # Case 1: If volume is same direction, find the average
        if (volume > 0 and self.orders_history["volume"] > 0) or (volume < 0 and self.orders_history["volume"] < 0):
            self.orders_history["price"] = (abs(volume) * price + abs(self.orders_history["volume"] * self.orders_history["price"])) // abs(new_vol)
            self.orders_history["volume"] = new_vol
        # Case 2: If volume is opposite direction, update accordingly
        else:
            if abs(volume) < abs(self.orders_history["volume"]):
                self.orders_history["volume"] = new_vol
            elif abs(volume) == abs(self.orders_history["volume"]):
                self.orders_history["price"] = 0
                self.orders_history["volume"] = 0
            else:
                self.orders_history["volume"] = new_vol
                self.orders_history["price"] = price
			
        hedged_pos_needed = -self.position
        if hedged_pos_needed > 0:
            hedged_pos_needed = min(0, hedged_pos_needed - 10)
        elif hedged_pos_needed < 0:
            hedged_pos_needed = max(0, hedged_pos_needed + 10)
		
        # If there are >= 10 unhedged positions at any point in time
        if self.hedge_position < hedged_pos_needed:
            # Buy more futures
            buy_pos = hedged_pos_needed - self.hedge_position
            order_id = next(self.order_ids)
            self.hedge_position += buy_pos
            self.send_hedge_order(order_id, Side.BID, MAX_ASK_NEAREST_TICK, buy_pos)
            self.hedge_bids.add(order_id)
        elif self.hedge_position > hedged_pos_needed:
            # Sell more futures
            sell_pos = self.hedge_position - hedged_pos_needed
            order_id = next(self.order_ids)
            self.hedge_position -= sell_pos
            self.send_hedge_order(order_id, Side.ASK, MIN_BID_NEAREST_TICK, sell_pos)
            self.hedge_asks.add(order_id)


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