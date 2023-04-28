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
from typing import Callable, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ready_trader_go.types import Instrument

from ready_trader_go.hud.table_gadget import BasicPriceLadderGadget, PerTeamTableGadget, ProfitLossTableGadget
from ready_trader_go.hud.table_model import (ActiveOrderTableModel, BasicPriceLadderModel,
                                             ProfitLossTableModel, TradeHistoryTableModel, PriceLadderModel,
                                             TeamLadderVolumes)
from ready_trader_go.hud.event_source import EventSource
from ready_trader_go.hud.chart import MidpointChartGadget, ProfitLossChartGadget

from .ui_main_window import Ui_main_window


TICK_SIZE: int = 100


class SubWindowEventFilter(QtCore.QObject):
    """Event filter for a sub window."""

    def __init__(self, callback: Callable, parent: Optional[QtCore.QObject] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)
        self.__callback: Callable = callback

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Capture close events and call a callback."""
        typ = event.type()
        if typ == QtCore.QEvent.Close:
            self.__callback()
            return False
        return super().eventFilter(source, event)


class MainWindow(Ui_main_window, QtWidgets.QMainWindow):
    """Main window for the Ready Trader Go heads-up display."""

    def __init__(self, icon: QtGui.QIcon, event_source: EventSource, parent: Optional[QtWidgets.QWidget] = None):
        """Initialise a new instance of the class."""
        QtWidgets.QMainWindow.__init__(self, parent)

        self.setupUi(self)

        self.setWindowTitle("Ready Trader Go")
        self.setWindowIcon(icon)
        self.__setup_menus()

        self.event_source: EventSource = event_source
        event_source.setParent(self)
        event_source.event_source_error_occurred.connect(self.__on_event_source_error_occurred)
        event_source.login_occurred.connect(self.__on_login_occurred)
        event_source.match_over.connect(self.__on_match_over)

        self.__icon: QtGui.QIcon = icon
        self.__team_active_orders: Dict[str, ActiveOrderTableModel] = dict()
        self.__team_trades: Dict[str, TradeHistoryTableModel] = dict()
        self.__team_volumes: Dict[str, TeamLadderVolumes] = dict()
        self.__selected_team: str = ""

        self.__setup_models()

    def __on_event_source_error_occurred(self, error_message: str) -> None:
        """Callback when an error occurs with the event source."""
        error_dialog = QtWidgets.QMessageBox(self)
        error_dialog.setIcon(QtWidgets.QMessageBox.Critical)
        error_dialog.setInformativeText(error_message)
        error_dialog.setWindowTitle("Error")
        error_dialog.setText("Error")
        error_dialog.show()

    def __on_login_occurred(self, competitor: str) -> None:
        """Callback when a login occurs."""
        aov_model = ActiveOrderTableModel(competitor)
        self.event_source.order_amended.connect(aov_model.on_order_amended)
        self.event_source.order_cancelled.connect(aov_model.on_order_cancelled)
        self.event_source.order_inserted.connect(aov_model.on_order_inserted)
        self.event_source.trade_occurred.connect(aov_model.on_trade_occurred)
        self.__team_active_orders[competitor] = aov_model

        competitor_volumes = TeamLadderVolumes(competitor)
        self.event_source.order_amended.connect(competitor_volumes.on_order_amended)
        self.event_source.order_cancelled.connect(competitor_volumes.on_order_cancelled)
        self.event_source.order_inserted.connect(competitor_volumes.on_order_inserted)
        self.event_source.trade_occurred.connect(competitor_volumes.on_trade_occurred)
        self.__team_volumes[competitor] = competitor_volumes

        tv_model = TradeHistoryTableModel(competitor)
        self.event_source.trade_occurred.connect(tv_model.on_trade_occurred)
        self.__team_trades[competitor] = tv_model

    def __on_match_over(self) -> None:
        """Callback when the Ready Trader Go match is over."""
        message_dialog = QtWidgets.QMessageBox(self)
        message_dialog.setIcon(QtWidgets.QMessageBox.Information)
        message_dialog.setInformativeText("The simulation is now complete.")
        message_dialog.setWindowTitle("Simulation Complete")
        message_dialog.setText("Simulation Complete")
        message_dialog.show()

    def __on_selected_competitor_changed(self, team: str) -> None:
        """Callback when the selected competitor changes."""
        if team and team != self.__selected_team:
            if self.__selected_team in self.__team_volumes:
                self.__team_volumes[self.__selected_team].clear_model()
            self.__selected_team = team
            if self.__aov and team in self.__team_active_orders:
                self.__aov.set_model(self.__team_active_orders[team])
            if team in self.__team_volumes:
                self.__etf_model.set_competitor_model(self.__team_volumes[team])
                self.__team_volumes[team].set_model(self.__etf_model)
                self.__etf_ladder.setWindowTitle("ETF (%s)" % team)
            if self.__tv and team in self.__team_trades:
                self.__tv.set_model(self.__team_trades[team])

    def __on_all_teams_profit_table_closed(self) -> None:
        """Callback when the all-teams profit table window is closed."""
        self.all_teams_profit_table_action.setEnabled(True)
        self.__pnl = None

    def __on_etf_dynamic_depth_closed(self) -> None:
        """Callback when the ETF dynamic depth window is closed."""
        self.etf_dynamic_depth_action.setEnabled(True)
        self.__etf_ladder = None

    def __on_future_dynamic_depth_closed(self) -> None:
        """Callback when the future dynamic depth window is closed."""
        self.future_dynamic_depth_action.setEnabled(True)
        self.__future_ladder = None

    def __on_team_active_order_table_closed(self) -> None:
        """Callback when the team active order table window is closed."""
        self.team_active_orders_table_action.setEnabled(True)
        self.__aov = None

    def __on_team_trade_history_table_closed(self) -> None:
        """Callback when the team trade history table window is closed."""
        self.team_trade_history_table_action.setEnabled(True)
        self.__tv = None

    def __on_midpoint_price_chart_closed(self) -> None:
        """Callback when the midpoint price chart is closed."""
        self.midpoint_price_chart_action.setEnabled(True)
        self.__mcg = None

    def __on_profit_loss_chart_closed(self) -> None:
        """Callback when the profit loss chart is closed."""
        self.profit_loss_chart_action.setEnabled(True)
        self.__pnl_chart = None

    def __show_sub_window(self, gadget: QtWidgets.QWidget, callback: Callable, width_fraction: float,
                          height_fraction: float) -> None:
        """Show a gadget as a sub-window."""
        width: int = round(width_fraction * self.mdi_area.width())
        height: int = round(height_fraction * self.mdi_area.height())
        sub_window: QtWidgets.QMdiSubWindow = self.mdi_area.addSubWindow(gadget)
        sub_window.installEventFilter(SubWindowEventFilter(callback, gadget))
        sub_window.resize(width, height)
        sub_window.setWindowIcon(self.__icon)
        sub_window.show()

    def __show_all_teams_profit_table(self) -> None:
        """Show the all-team profit or loss table."""
        self.all_teams_profit_table_action.setEnabled(False)
        self.__pnl = ProfitLossTableGadget(self)
        self.__pnl.set_model(self.__pnl_model)
        self.__show_sub_window(self.__pnl, self.__on_all_teams_profit_table_closed, 0.49, 0.4)

    def __show_etf_dynamic_depth(self) -> None:
        """Show the ETF Dynamic Depth window."""
        self.etf_dynamic_depth_action.setEnabled(False)
        self.__etf_ladder = BasicPriceLadderGadget(self)
        self.__etf_ladder.set_model(self.__etf_model)
        if self.__selected_team and self.__selected_team in self.__team_volumes:
            self.__etf_ladder.setWindowTitle("ETF (%s)" % self.__selected_team)
        self.__show_sub_window(self.__etf_ladder, self.__on_etf_dynamic_depth_closed, 0.30, 0.4)

    def __show_future_dynamic_depth(self) -> None:
        """Show the Future Dynamic Depth window."""
        self.future_dynamic_depth_action.setEnabled(False)
        self.__future_ladder = BasicPriceLadderGadget(self)
        self.__future_ladder.set_model(self.__future_model)
        self.__show_sub_window(self.__future_ladder, self.__on_future_dynamic_depth_closed, 0.21, 0.4)

    def __show_team_active_order_table(self) -> None:
        """Show the team active orders table."""
        self.team_active_orders_table_action.setEnabled(False)
        self.__aov = PerTeamTableGadget("Active Orders", self)
        if self.__selected_team and self.__selected_team in self.__team_active_orders:
            self.__aov.set_model(self.__team_active_orders[self.__selected_team])
        self.__show_sub_window(self.__aov, self.__on_team_active_order_table_closed, 0.45, 0.3)

    def __show_team_trade_history_table(self) -> None:
        """Show the team trade history table."""
        self.team_trade_history_table_action.setEnabled(False)
        self.__tv = PerTeamTableGadget("Trade History", self)
        if self.__selected_team and self.__selected_team in self.__team_trades:
            self.__tv.set_model(self.__team_trades[self.__selected_team])
        self.__show_sub_window(self.__tv, self.__on_team_trade_history_table_closed, 0.45, 0.3)

    def __show_midpoint_price_chart(self) -> None:
        """Show the midpoint price chart."""
        self.midpoint_price_chart_action.setEnabled(False)
        self.__mcg = MidpointChartGadget(self)
        self.event_source.midpoint_price_changed.connect(self.__mcg.on_midpoint_price_changed)
        self.__show_sub_window(self.__mcg, self.__on_midpoint_price_chart_closed, 0.55, 0.3)

    def __show_profit_loss_chart(self) -> None:
        """Show the all-teams profit loss chart."""
        self.profit_loss_chart_action.setEnabled(False)
        self.__pnl_chart = ProfitLossChartGadget(self)
        self.event_source.login_occurred.connect(self.__pnl_chart.on_login_occurred)
        self.event_source.profit_loss_changed.connect(self.__pnl_chart.on_profit_loss_changed)
        for team in self.__team_volumes.keys():
            self.__pnl_chart.on_login_occurred(team)
        self.__show_sub_window(self.__pnl_chart, self.__on_profit_loss_chart_closed, 0.55, 0.3)

    def __setup_menus(self) -> None:
        """Setup the menu bar menus for this main window."""
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.setStatusTip("Exit application")
        self.quit_action.triggered.connect(self.close)

        self.etf_dynamic_depth_action.setStatusTip("Reopen the ETF dynamic depth window")
        self.etf_dynamic_depth_action.triggered.connect(self.__show_etf_dynamic_depth)

        self.future_dynamic_depth_action.setStatusTip("Reopen the Future dynamic depth window")
        self.future_dynamic_depth_action.triggered.connect(self.__show_future_dynamic_depth)

        self.all_teams_profit_table_action.setStatusTip("Reopen the profit loss table")
        self.all_teams_profit_table_action.triggered.connect(self.__show_all_teams_profit_table)

        self.team_active_orders_table_action.setStatusTip("Reopen the active orders table")
        self.team_active_orders_table_action.triggered.connect(self.__show_team_active_order_table)

        self.team_trade_history_table_action.setStatusTip("Reopen the trade history table")
        self.team_trade_history_table_action.triggered.connect(self.__show_team_trade_history_table)

        self.midpoint_price_chart_action.setStatusTip("Reopen the midpoint price chart")
        self.midpoint_price_chart_action.triggered.connect(self.__show_midpoint_price_chart)

        self.profit_loss_chart_action.setStatusTip("Reopen the profit or loss chart")
        self.profit_loss_chart_action.triggered.connect(self.__show_profit_loss_chart)

    def __setup_models(self) -> None:
        """Setup the data models."""
        self.__etf_model = PriceLadderModel(Instrument.ETF, TICK_SIZE)
        self.event_source.order_book_changed.connect(self.__etf_model.update_order_book)
        self.__future_model = BasicPriceLadderModel(Instrument.FUTURE, TICK_SIZE)
        self.event_source.order_book_changed.connect(self.__future_model.update_order_book)
        self.__pnl_model = ProfitLossTableModel()
        self.__pnl_model.team_changed.connect(self.__on_selected_competitor_changed)
        self.event_source.login_occurred.connect(self.__pnl_model.on_login_occurred)
        self.event_source.profit_loss_changed.connect(self.__pnl_model.on_profit_loss_changed)

    def show(self) -> None:
        """Show the window."""
        QtWidgets.QMainWindow.show(self)

        self.__show_future_dynamic_depth()
        self.__show_etf_dynamic_depth()
        self.__show_all_teams_profit_table()
        self.__show_team_active_order_table()
        self.__show_midpoint_price_chart()
        self.__show_team_trade_history_table()
        self.__show_profit_loss_chart()

        self.event_source.start()
