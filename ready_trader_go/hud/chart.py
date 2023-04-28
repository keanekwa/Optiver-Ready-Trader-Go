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

from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6 import QtCharts
from PySide6.QtCore import Qt

from ready_trader_go.types import Instrument

CHART_DURATION: float = 60.0


class BaseChartGadget(QtWidgets.QWidget):
    """A generic chart widget."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, flags: Qt.WindowFlags = Qt.Widget):
        """Initialise a new instance of the class."""
        super().__init__(parent, flags)

        self.chart_view = QtCharts.QChartView()
        self.chart_view.setRenderHint(QtGui.QPainter.Antialiasing)

        chart: QtCharts.QChart = self.chart_view.chart()
        chart.legend().setLabelColor(parent.palette().color(parent.foregroundRole()))
        chart.setAnimationDuration(500)
        chart.setAnimationEasingCurve(QtCore.QEasingCurve.Linear)
        chart.setAnimationOptions(QtCharts.QChart.NoAnimation)
        chart.setBackgroundBrush(parent.palette().color(parent.backgroundRole()))
        chart.setBackgroundRoundness(0.0)
        chart.setContentsMargins(-7, -7, -7, -7)
        chart.setMargins(QtCore.QMargins(10, 0, 10, 10))
        self.chart: QtCharts.QChart = chart

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.chart_view)
        self.setLayout(layout)

        x_axis = QtCharts.QValueAxis()
        x_axis.setRange(-CHART_DURATION, 0.0)
        y_axis = QtCharts.QValueAxis()
        self.chart.addAxis(x_axis, QtCore.Qt.AlignBottom)
        self.chart.addAxis(y_axis, QtCore.Qt.AlignLeft)
        self._style_axes()

        self._largest_y_value: float = 0.0
        self._smallest_y_value: float = sys.float_info.max
        self.__x_axis_maximum: float = 0.0

    def _style_axes(self):
        """Apply the common style elements to the chart axes."""
        chart: QtCharts.QChart = self.chart
        # chart.axisX().setGridLineColor(QtGui.QColor("#F0F0F0"))
        chart.axisX().setLabelsColor(chart.legend().labelColor())
        chart.axisY().setLabelFormat("%.2f")
        chart.axisY().setLabelsColor(chart.legend().labelColor())

    def _scroll_x_axis(self, time: float) -> None:
        """Scroll the the x-axis to the given time."""
        if time > self.__x_axis_maximum:
            scroll_distance: float = time - self.__x_axis_maximum
            self.__x_axis_maximum += scroll_distance
            self.chart.scroll(scroll_distance * self.chart.plotArea().width() / CHART_DURATION, 0)

    def _update_y_axis(self, new_value: float) -> None:
        """Ensure the y-axis range is large enough for the given value."""
        if new_value < self._smallest_y_value:
            self.chart.axisY().setMin(new_value - 0.01)
            self._smallest_y_value = new_value
        if new_value > self._largest_y_value:
            self.chart.axisY().setMax(new_value + 0.01)
            self._largest_y_value = new_value


class MidpointChartGadget(BaseChartGadget):
    """A chart of midpoint prices."""

    _COLOURS = (QtGui.QColor("#E8755A"), QtGui.QColor("#3DAEE9"))

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)

        self.setWindowTitle("Midpoint Prices")

        self.instrument_series: List[QtCharts.QSplineSeries] = [QtCharts.QSplineSeries() for _ in Instrument]
        for i, line_series in enumerate(self.instrument_series):
            line_series.setName(Instrument(i).name)
            self.chart.addSeries(line_series)
            line_series.attachAxis(self.chart.axisX())
            line_series.attachAxis(self.chart.axisY())
            line_series.setColor(self._COLOURS[i])

        self.__last_price: Optional[float] = None
        self.__timer = QtCore.QTimer(self)
        self.__timer.timeout.connect(self.__on_timer_tick)

    def __on_timer_tick(self) -> None:
        delta: float = (self._largest_y_value - self._smallest_y_value) // 8
        if delta:
            high_distance: float = self._largest_y_value - self.__last_price
            low_distance: float = self.__last_price - self._smallest_y_value
            if high_distance > low_distance:
                self._largest_y_value -= delta
            else:
                self._smallest_y_value += delta
            self.chart.axisY().setRange(self._smallest_y_value, self._largest_y_value)

    def on_midpoint_price_changed(self, instrument: Instrument, time: float, mid_price: float) -> None:
        """Callback when the midpoint price of an instrument changes."""
        self._scroll_x_axis(time)
        price = mid_price / 100.0
        self._update_y_axis(price)
        self.instrument_series[instrument].append(time, price)
        self.__last_price = price
        if not self.__timer.isActive():
            self.__timer.start(6000)


class ProfitLossChartGadget(BaseChartGadget):
    """A chart of the profit, or loss, of each team."""

    _COLOURS = ("#E8755A", "#3DAEE9", "#23CC69", "#F5C60B", "#EF7E1B", "#A95FC8", "#85E8D5", "#85B0DC")

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        """Initialise a new instance of the class."""
        super().__init__(parent)

        self.setWindowTitle("All Teams Profit or Loss")
        self.team_series: Dict[str, QtCharts.QSplineSeries] = collections.defaultdict(QtCharts.QSplineSeries)

    def on_login_occurred(self, team: str) -> None:
        """Callback when a team logs in to the exchange."""
        line_series: QtCharts.QSplineSeries = self.team_series[team]
        self.chart.addSeries(line_series)
        line_series.attachAxis(self.chart.axisX())
        line_series.attachAxis(self.chart.axisY())
        line_series.setName(team)
        line_series.setColor(self._COLOURS[(len(self.team_series) - 1) % len(self._COLOURS)])

    def on_profit_loss_changed(self, team: str, time: float, profit: float, etf_position: int,
                               account_balance: float, total_fees: float) -> None:
        """Callback when the profit of a team changes."""
        self._update_y_axis(profit)
        self.team_series[team].append(time, profit)
        self._scroll_x_axis(time)
