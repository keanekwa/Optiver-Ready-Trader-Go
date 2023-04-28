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

from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from ready_trader_go.types import Instrument, Lifespan, Side

_ALIGN_CENTER_LEFT = int(Qt.AlignLeft) | int(Qt.AlignVCenter)
_ALIGN_CENTER_RIGHT = int(Qt.AlignRight) | int(Qt.AlignVCenter)


class BaseTableModel(QtCore.QAbstractTableModel):
    """Base data model for table."""

    # Subclass should override these
    _COLUMN_NAME = tuple()
    _COLUMN_ALIGNMENTS = tuple()
    _COLUMN_TOOLTIPS = tuple()

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._row_count: int = 0

    def columnCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        """Return the number of columns."""
        return len(self._COLUMN_NAMES) if parent is None or not parent.isValid() else 0

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return information about a specified table cell."""
        column = index.column()
        if role == Qt.TextAlignmentRole:
            return self._COLUMN_ALIGNMENTS[column]
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return information about a specified table header cell."""
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self._COLUMN_NAMES[section]
            if role == Qt.ToolTipRole:
                return self._COLUMN_TOOLTIPS[section]
        return None

    def rowCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        """Return the number of rows."""
        return self._row_count if parent is None or not parent.isValid() else 0


class ActiveOrderTableModel(BaseTableModel):
    """Data model for the per-team active orders table."""

    _COLUMN_NAMES = ("Time", "OrderId", "Inst.", "Side", "Volume", "Price")
    _COLUMN_ALIGNMENTS = (_ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT, Qt.AlignCenter, Qt.AlignCenter,
                          _ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT)
    _COLUMN_TOOLTIPS = ("Time when the order was placed",
                        "Order identifier",
                        "The instrument to be traded",
                        "The side of the order (either buy or sell)",
                        "The volume of the order (i.e. the number of lots to trade)",
                        "The limit price of the order (i.e. the worst price at which it can trade)")
    _ORDER_ID_COLUMN = _COLUMN_NAMES.index("OrderId")
    _VOLUME_COLUMN = _COLUMN_NAMES.index("Volume")

    def __init__(self, team: str, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)
        self.team: str = team
        self.__orders: List[List[str, int, str, str, int, str]] = list()

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return information about a specified table cell."""
        if role == Qt.DisplayRole:
            return self.__orders[self._row_count - index.row() - 1][index.column()]
        return super().data(index, role)

    def __remove_row(self, row: int) -> None:
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        self._row_count -= 1
        self.__orders.pop(row)
        self.endRemoveRows()

    def __update_order_volume(self, order_id: int, volume_delta: int) -> None:
        row = next((i for i in range(self._row_count) if self.__orders[i][self._ORDER_ID_COLUMN] == order_id), None)
        if row is not None:
            self.__orders[row][self._VOLUME_COLUMN] += volume_delta
            if self.__orders[row][self._VOLUME_COLUMN] <= 0:
                self.__remove_row(row)
            else:
                self.dataChanged.emit(self.createIndex(row, self._VOLUME_COLUMN),
                                      self.createIndex(row, self._VOLUME_COLUMN))

    def on_order_amended(self, team: str, _: float, order_id: int, volume_delta: int) -> None:
        """Callback when an order is amended."""
        if team == self.team:
            self.__update_order_volume(order_id, volume_delta)

    def on_order_cancelled(self, team: str, now: float, order_id: int) -> None:
        """Callback when an order is cancelled."""
        if team == self.team:
            row = next((i for i in range(self._row_count) if self.__orders[i][self._ORDER_ID_COLUMN] == order_id), None)
            if row is not None:
                self.__remove_row(row)

    def on_order_inserted(self, team: str, now: float, order_id: int, instrument: Instrument, side: Side,
                          volume: int, price: int, _: Lifespan) -> None:
        """Callback when an order is inserted."""
        if team == self.team:
            self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
            self._row_count += 1
            self.__orders.append(["%.3f" % now, order_id, instrument.name, side.name.capitalize(), volume,
                                  "%.2f" % (price / 100.0)])
            self.endInsertRows()

    def on_trade_occurred(self, team: str, now: float, order_id: int, side: Side, volume: int, price: int,
                          fee: int) -> None:
        """Callback when a trade occurs."""
        if team == self.team:
            self.__update_order_volume(order_id, -volume)


class BasicPriceLadderModel(BaseTableModel):
    """Table model for a basic price ladder."""

    _ASK_VOL_COLUMN = 2
    _BID_VOL_COLUMN = 0
    _COLUMN_NAMES = ("BidVol", "Price", "AskVol")
    _COLUMN_ALIGNMENTS = (Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter)
    _COLUMN_TOOLTIPS = ("Total bid volume available at each price level",
                        None,
                        "Total ask volume available at each price level")
    _MINIMUM_EXTRA_ROW_COUNT = 50
    _PRICE_COLUMN = 1

    # Signals
    best_ask_row_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, instrument: Instrument, tick_size: int, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)

        self.instrument: Instrument = instrument
        self.last_best_ask: int = 0
        self.last_best_ask_row: int = 0
        self.last_best_bid: int = 0
        self.tick_size: int = tick_size

        self._first_price: int = 0

        self.__ask_volumes: Dict[int, Any] = dict()
        self.__bid_volumes: Dict[int, Any] = dict()

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return the content of a table cell."""
        price = self._first_price - index.row() * self.tick_size
        column: int = index.column()
        if role == Qt.DisplayRole:
            if column == self._BID_VOL_COLUMN:
                return self.__bid_volumes.get(price, None)
            elif column == self._PRICE_COLUMN:
                return "%.2f" % (price / 100.0)
            elif column == self._ASK_VOL_COLUMN:
                return self.__ask_volumes.get(price, None)
        elif role == Qt.ForegroundRole:
            if column == self._PRICE_COLUMN:
                if price >= self.last_best_ask:
                    return QtGui.QColor("#E8755A")
                if price <= self.last_best_bid:
                    return QtGui.QColor("#3DAEE9")

        return super().data(index, role)

    def get_row(self, price: int) -> int:
        """Return the row for a given price."""
        return self._first_price - price // self.tick_size

    def get_price(self, row: int) -> int:
        """Return the price for a given row."""
        return self._first_price - row * self.tick_size

    def __append_rows(self, count: int) -> None:
        self.beginInsertRows(QtCore.QModelIndex(), self._row_count, self._row_count + count - 1)
        self._row_count += count
        self.endInsertRows()

    def __prepend_rows(self, count: int) -> None:
        self.beginInsertRows(QtCore.QModelIndex(), 1, count)
        self._row_count += count
        self._first_price += count * self.tick_size
        self.endInsertRows()

    def update_order_book(self, instrument: Instrument, _: float, ask_prices: List[int], ask_volumes: List[int],
                          bid_prices: List[int], bid_volumes: List[int],) -> None:
        """Callback when the order book changes."""
        if instrument != self.instrument:
            return

        best_ask: int = ask_prices[0]
        if best_ask == 0 and bid_prices[0] != 0:
            best_ask = bid_prices[0] + self.tick_size

        min_best_ask: int = best_ask if best_ask < self.last_best_ask else self.last_best_ask
        max_best_ask: int = best_ask if best_ask > self.last_best_ask else self.last_best_ask
        self.last_best_ask = best_ask
        self.last_best_bid = bid_prices[0]

        if self._first_price == 0:
            if best_ask == 0:
                return

            self._first_price = best_ask

        best_ask_row = (self._first_price - best_ask) // self.tick_size
        if best_ask_row < self._MINIMUM_EXTRA_ROW_COUNT:
            extra_row_count: int = self._MINIMUM_EXTRA_ROW_COUNT * 2 - best_ask_row
            self.__prepend_rows(extra_row_count)
            best_ask_row += extra_row_count
        if self._row_count - best_ask_row < self._MINIMUM_EXTRA_ROW_COUNT:
            self.__append_rows(best_ask_row + self._MINIMUM_EXTRA_ROW_COUNT * 2 - self._row_count)

        min_best_ask_row: int = (self._first_price - min_best_ask) // self.tick_size
        max_best_bid_row: int = (self._first_price - max_best_ask) // self.tick_size + 1

        self.__ask_volumes.clear()
        self.__ask_volumes.update((p, "{:,}".format(v)) for p, v in zip(ask_prices, ask_volumes) if p)
        self.dataChanged.emit(self.createIndex(0, self._ASK_VOL_COLUMN),
                              self.createIndex(min_best_ask_row, self._ASK_VOL_COLUMN))

        self.__bid_volumes.clear()
        self.__bid_volumes.update((p, "{:,}".format(v)) for p, v in zip(bid_prices, bid_volumes) if p)
        self.dataChanged.emit(self.createIndex(max_best_bid_row, self._BID_VOL_COLUMN),
                              self.createIndex(self._row_count - 1, self._BID_VOL_COLUMN))

        if best_ask_row != self.last_best_ask_row:
            self.last_best_ask_row = best_ask_row
            self.best_ask_row_changed.emit(best_ask_row)


class _Order:
    __slots__ = ("price", "remaining_volume")

    def __init__(self, price: int, volume: int):
        self.price: int = price
        self.remaining_volume: int = volume


class PriceLadderModel(BasicPriceLadderModel):
    """Table model for a price ladder."""

    _ASK_VOL_COLUMN = 3
    _BID_VOL_COLUMN = 1
    _COLUMN_NAMES = ("TeamBid", "BidVol", "Price", "AskVol", "TeamAsk")
    _COLUMN_ALIGNMENTS = (Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter)
    _COLUMN_TOOLTIPS = ("Bid volume for the selected team",
                        "Total bid volume available at each price level",
                        None,
                        "Total ask volume available at each price level",
                        "Ask volume for the selected team")
    _PRICE_COLUMN = 2
    TEAM_ASK_COLUMN = 4
    TEAM_BID_COLUMN = 0

    def __init__(self, instrument: Instrument, tick_size: int, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(instrument, tick_size, parent)
        self.__team_volumes = None

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return the content of a table cell."""
        if role == Qt.DisplayRole and self.__team_volumes:
            column: int = index.column()
            if column == self.TEAM_ASK_COLUMN or column == self.TEAM_BID_COLUMN:
                price = super().get_price(index.row())
                if column == self.TEAM_ASK_COLUMN:
                    return self.__team_volumes.team_ask_volumes.get(price, None)
                return self.__team_volumes.team_bid_volumes.get(price, None)

        return super().data(index, role)

    def set_competitor_model(self, team_volumes):
        self.__team_volumes = team_volumes
        self.createIndex(0, self.TEAM_BID_COLUMN)
        self.dataChanged.emit(self.createIndex(0, self.TEAM_BID_COLUMN),
                              self.createIndex(self._row_count, self.TEAM_BID_COLUMN))
        self.dataChanged.emit(self.createIndex(0, self.TEAM_ASK_COLUMN),
                              self.createIndex(self._row_count, self.TEAM_ASK_COLUMN))


class TeamLadderVolumes:
    """A team's ask and bid volumes for each price level."""

    def __init__(self, team: str):
        """Initialise a new instance of the class."""
        super().__init__()

        self.team = team
        self.team_ask_volumes: Dict[int, int] = collections.defaultdict(int)
        self.team_bid_volumes: Dict[int, int] = collections.defaultdict(int)

        self.__ask_orders: Dict[int, _Order] = dict()
        self.__bid_orders: Dict[int, _Order] = dict()
        self.__model: Optional[PriceLadderModel] = None

    def clear_model(self) -> None:
        """Clear the price ladder model."""
        self.__model = None

    def set_model(self, model: PriceLadderModel) -> None:
        """Set the price ladder model."""
        self.__model = model

    def __subtract_volume(self, order_id: int, volume: int) -> None:
        if order_id in self.__ask_orders:
            order = self.__ask_orders[order_id]
            order.remaining_volume -= volume
            if order.remaining_volume == 0:
                del self.__ask_orders[order_id]
            self.team_ask_volumes[order.price] -= volume
            if self.team_ask_volumes[order.price] == 0:
                del self.team_ask_volumes[order.price]
        elif order_id in self.__bid_orders:
            order = self.__bid_orders[order_id]
            order.remaining_volume -= volume
            if order.remaining_volume == 0:
                del self.__bid_orders[order_id]
            self.team_bid_volumes[order.price] -= volume
            if self.team_bid_volumes[order.price] == 0:
                del self.team_bid_volumes[order.price]
        else:
            return

        if self.__model:
            column: int = (self.__model.TEAM_ASK_COLUMN if order_id in self.__ask_orders
                           else self.__model.TEAM_BID_COLUMN)
            index = self.__model.createIndex(self.__model.get_row(order.price), column)
            self.__model.dataChanged.emit(index, index)

    def on_order_amended(self, team: str, now: float, order_id: int, volume_delta: int) -> None:
        """Callback when an order is amended."""
        if team == self.team:
            self.__subtract_volume(order_id, -volume_delta)

    def on_order_cancelled(self, team: str, now: float, order_id: int) -> None:
        """Callback when an order is cancelled."""
        if team == self.team:
            if order_id in self.__ask_orders:
                self.__subtract_volume(order_id, self.__ask_orders[order_id].remaining_volume)
            elif order_id in self.__bid_orders:
                self.__subtract_volume(order_id, self.__bid_orders[order_id].remaining_volume)

    def on_order_inserted(self, team: str, now: float, order_id: int, instrument: Instrument, side: Side,
                          volume: int, price: int, lifespan: Lifespan) -> None:
        """Callback when an order is inserted."""
        if team == self.team:
            if side == Side.SELL:
                self.__ask_orders[order_id] = _Order(price, volume)
                self.team_ask_volumes[price] += volume
            else:
                self.__bid_orders[order_id] = _Order(price, volume)
                self.team_bid_volumes[price] += volume

            if self.__model:
                column: int = self.__model.TEAM_ASK_COLUMN if side == Side.SELL else self.__model.TEAM_BID_COLUMN
                index = self.__model.createIndex(self.__model.get_row(price), column)
                self.__model.dataChanged.emit(index, index)

    def on_trade_occurred(self, team: str, now: float, order_id: int, side: Side, volume: int, price: int,
                          fee: int) -> None:
        """Callback when a trade occurs."""
        if team == self.team:
            self.__subtract_volume(order_id, volume)


class ProfitLossTableModel(BaseTableModel):
    """Data model for the all-teams profit or loss table."""

    _COLOURS = (QtGui.QColor("#E8755A"), QtGui.QColor("#23CC69"))
    _COLUMN_NAMES = ("Team", "ETF", "Fut", "Value", "TrdProfit", "TotFees", "NetProfit")
    _COLUMN_ALIGNMENTS = (_ALIGN_CENTER_LEFT, _ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT,
                          _ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT,
                          _ALIGN_CENTER_RIGHT)
    _COLUMN_TOOLTIPS = ("Team name",
                        "ETF position",
                        "Future position",
                        "Value of position (based on last-traded price of ETF and Future)",
                        "Profit (if positive) or loss (if negative) from trading activity",
                        "Total fees collected (if positive) or paid (if negative)",
                        "Net profit (if positive) or loss (if negative) after fees")
    ETF_POSITION_COLUMN = _COLUMN_NAMES.index("ETF")
    FUT_POSITION_COLUMN = _COLUMN_NAMES.index("Fut")
    NET_PROFIT_COLUMN = _COLUMN_NAMES.index("NetProfit")
    TEAM_NAME_COLUMN = _COLUMN_NAMES.index("Team")

    # Signals
    team_changed = QtCore.Signal(str)  # Team name

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)
        self.__teams: Dict[str, int] = dict()
        self.__profits: List[List] = list()

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return information about the specified table cell."""
        if role == Qt.DisplayRole:
            column: int = index.column()
            value: Any = self.__profits[index.row()][column]
            if column == self.TEAM_NAME_COLUMN:
                return value
            elif column in (self.ETF_POSITION_COLUMN, self.FUT_POSITION_COLUMN):
                return str(value)
            else:
                return "$%.2f" % value
        elif role == Qt.ForegroundRole:
            profit: float = self.__profits[index.row()][self.NET_PROFIT_COLUMN]
            if profit < 0.0:
                return self._COLOURS[0]
            elif profit > 0.0:
                return self._COLOURS[1]
        elif role == Qt.UserRole:
            # Return the raw value (used for sorting)
            return self.__profits[index.row()][index.column()]
        return super().data(index, role)

    def on_login_occurred(self, team: str) -> None:
        """Callback when a team logs in."""
        if team not in self.__teams:
            team_number: int = len(self.__teams)
            self.beginInsertRows(QtCore.QModelIndex(), team_number, team_number)
            self.__teams[team] = team_number
            self.__profits.append([team, 0, 0, 0.0, 0.0, 0.0, 0.0])
            self._row_count += 1
            self.endInsertRows()

    def on_selection_changed(self, selected: QtCore.QItemSelection, _: QtCore.QItemSelection) -> None:
        """Callback when the selected team changes."""
        indexes: List[QtCore.QModelIndex] = selected.indexes()
        self.team_changed.emit(self.__profits[indexes[0].row()][0] if indexes else "")

    def on_profit_loss_changed(self, team: str, _: float, profit: float, etf_position: int,
                               fut_position: int, account_balance: float, total_fees: float) -> None:
        """Callback when the profit for a team changes."""
        row = self.__teams[team]
        self.__profits[row][1:] = (etf_position, fut_position, profit - account_balance, account_balance + total_fees,
                                   -total_fees, profit)
        self.dataChanged.emit(self.createIndex(row, 1), self.createIndex(row, len(self._COLUMN_NAMES) - 1))


class TradeHistoryTableModel(BaseTableModel):
    """Data model for the per-team trade history table."""

    _COLUMN_NAMES = ("Time", "OrderId", "Side", "Volume", "Price", "Fee")
    _COLUMN_ALIGNMENTS = (_ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT, Qt.AlignCenter, _ALIGN_CENTER_RIGHT,
                          _ALIGN_CENTER_RIGHT, _ALIGN_CENTER_RIGHT)
    _COLUMN_TOOLTIPS = ("Time when the trade occurred",
                        "Order identifier of the order that traded",
                        "The side of the order than traded (either buy or sell)",
                        "The number of lots that traded at this time",
                        "The price at which the trade occurred (which may be better than the order's limit price)",
                        "The fees collected (if positive) or paid (if negative) for this trade")

    def __init__(self, team: str, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)
        self.team: str = team
        self.__trades: List[Tuple[str, int, str, int, str, str]] = list()

    def data(self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return information about the specified table cell."""
        if role == Qt.DisplayRole:
            return self.__trades[self._row_count - index.row() - 1][index.column()]
        return super().data(index, role)

    def on_trade_occurred(self, team: str, now: float, order_id: int, side: Side, volume: int, price: int,
                          fee: int) -> None:
        """Callback when a trade occurs."""
        if team == self.team:
            self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
            self._row_count += 1
            self.__trades.append(("%.3f" % now, order_id, ("Sell", "Buy")[side], volume, "%.2f" % (price / 100.0),
                                  "%.2f" % (-fee / 100.0)))
            self.endInsertRows()
