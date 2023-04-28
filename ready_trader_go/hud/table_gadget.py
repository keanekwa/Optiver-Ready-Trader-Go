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
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ready_trader_go.types import Instrument
from .table_model import BasicPriceLadderModel, ProfitLossTableModel


class BaseTableGadget(QtWidgets.QWidget):
    """A gadget showing information in a table."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, flags: Qt.WindowFlags = Qt.Widget):
        """Initialise a new instance of the class."""
        super().__init__(parent, flags)

        self._verticalLayout = QtWidgets.QVBoxLayout(self)
        self._verticalLayout.setObjectName(u"verticalLayout")

        self._table_view = QtWidgets.QTableView(self)
        self._table_view.setObjectName("base_table_view")
        self._table_view.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self._table_view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table_view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self._table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self._table_view.verticalHeader().setVisible(False)

        font_height = QtGui.QFontMetrics(self._table_view.font()).height()
        self._table_view.verticalHeader().setMinimumSectionSize(font_height + 2)
        self._table_view.verticalHeader().setDefaultSectionSize(font_height + 2)

        self._verticalLayout.addWidget(self._table_view)


class LadderEventFilter(QtCore.QObject):
    """Event filter for the basic price ladder."""

    def __init__(self, ladder_gadget: QtWidgets.QWidget):
        """Initialise a new instance of the class."""
        super().__init__(ladder_gadget)
        self.ladder_gadget: QtWidgets.QWidget = ladder_gadget

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Handle resize and filter out mouse events."""
        typ = event.type()
        if typ == QtCore.QEvent.Resize:
            self.ladder_gadget.update_best_ask_row(self.ladder_gadget.last_best_ask_row)
            return False

        if typ in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonDblClick,
                   QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseMove, QtCore.QEvent.Wheel):
            return True

        return super().eventFilter(source, event)


class BasicPriceLadderGadget(BaseTableGadget):
    """A price ladder showing prices and volumes."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, flags: Qt.WindowFlags = Qt.Widget):
        """Initialise a new instance of the class."""
        super().__init__(parent, flags)

        self.last_best_ask_row: int = 0
        self.last_best_ask: int = 0

        self._table_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table_view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self._table_view.viewport().installEventFilter(LadderEventFilter(self))

        self.__animation = QtCore.QVariantAnimation()
        self.__animation.valueChanged.connect(self.__on_animation_value_changed)

    def set_model(self, table_model: BasicPriceLadderModel):
        """Set the data model for this price ladder."""
        if self._table_view.model() is not None:
            self._table_view.model().best_ask_row_changed.disconnect(self.update_best_ask_row)

        self._table_view.setModel(table_model)
        self.setWindowTitle("Future" if table_model.instrument == Instrument.FUTURE else "ETF")
        table_model.best_ask_row_changed.connect(self.update_best_ask_row)
        self.update_best_ask_row(table_model.last_best_ask_row)

    def __on_animation_value_changed(self, value):
        """Scroll the best ask price toward the vertical center on each animation tick."""
        self._table_view.verticalScrollBar().setValue(value)

    def update_best_ask_row(self, new_best_ask_row: int) -> None:
        """Update the best ask row and ensure it is centered in the display."""
        if self.last_best_ask_row != new_best_ask_row:
            self.last_best_ask_row = new_best_ask_row

            if self.__animation.state() == QtCore.QAbstractAnimation.Running:
                self.__animation.stop()

            row_height: int = self._table_view.verticalHeader().defaultSectionSize()
            viewport_height: int = self._table_view.viewport().height()
            asks_height: int = (self.last_best_ask_row + 1) * row_height

            self.__animation.setStartValue(self._table_view.verticalScrollBar().value())
            self.__animation.setEndValue(asks_height - viewport_height // 2)
            self.__animation.setDuration(500)
            self.__animation.start()


class PerTeamTableGadget(BaseTableGadget):
    """A gadget showing information about a team."""

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None,
                 flags: Qt.WindowFlags = Qt.Widget):
        """Initialise a new instance of the class."""
        super().__init__(parent, flags)
        self.title: str = title
        self.setWindowTitle(title)
        self._table_view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

    def set_model(self, table_model: QtCore.QAbstractTableModel) -> None:
        """Set the table model used for this table gadget."""
        self._table_view.setModel(table_model)
        self._table_view.reset()
        self.setWindowTitle("%s for %s" % (self.title, table_model.team))


class ProfitLossTableGadget(BaseTableGadget):
    """A gadget showing the profit, or loss, of all teams."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, flags: Qt.WindowFlags = Qt.Widget):
        """Initialise a new instance of the class."""
        super().__init__(parent, flags)

        self.setWindowTitle("All Teams Profit or Loss")

        self._table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        self.select_team_label = QtWidgets.QLabel(self)
        self.select_team_label.setText("Select a team to see their active orders and trade history:")
        self._verticalLayout.insertWidget(0, self.select_team_label)

        self.__proxy_model: Optional[QtCore.QSortFilterProxyModel] = None
        self.__profit_model: Optional[ProfitLossTableModel] = None

    def __on_rows_inserted(self, parent: QtCore.QModelIndex, first: int, last: int) -> None:
        self._table_view.selectionModel().select(self._table_view.model().index(0, 0),
                                                 QtCore.QItemSelectionModel.ClearAndSelect
                                                 | QtCore.QItemSelectionModel.Rows)
        self.__proxy_model.rowsInserted.disconnect(self.__on_rows_inserted)

    def __selection_changed(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection) -> None:
        self.__profit_model.on_selection_changed(self.__proxy_model.mapSelectionToSource(selected),
                                                 self.__proxy_model.mapSelectionToSource(deselected))

    def set_model(self, table_model: ProfitLossTableModel) -> None:
        """Set the data model for this table gadget."""
        self.__profit_model = table_model
        self.__proxy_model = QtCore.QSortFilterProxyModel(self)
        self.__proxy_model.setSortRole(Qt.UserRole)
        self.__proxy_model.setSourceModel(table_model)
        self._table_view.setModel(self.__proxy_model)
        self._table_view.selectionModel().selectionChanged.connect(self.__selection_changed)
        self._table_view.setSortingEnabled(True)
        self._table_view.sortByColumn(self.__profit_model.NET_PROFIT_COLUMN, Qt.SortOrder.DescendingOrder)
        if table_model.rowCount() == 0:
            self.__proxy_model.rowsInserted.connect(self.__on_rows_inserted)
