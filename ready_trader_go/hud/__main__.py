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
import configparser
import json
import os
import pathlib
import string
import sys
import time

from typing import Any, Mapping, Tuple

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt

from .event_source import EventSource, LiveEventSource, RecordedEventSource
from .main_window.main_window import MainWindow


HERE: pathlib.Path = pathlib.Path(__file__).parent
DEFAULT_ETF_CLAMP: float = 0.002
DEFAULT_TICK_SIZE: float = 0.01
EXCHANGE_CONFIG_PATH = "exchange.json"


def __create_application() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    with (HERE.joinpath("style/style.qss")).open("r") as theme:
        with (HERE.joinpath("style/settings.ini")).open("r") as settings:
            parser = configparser.ConfigParser()
            parser.read_file(settings)
            template = string.Template(theme.read())
            app.setStyleSheet(template.substitute(parser["default"]))
    return app


def __read_exchange_config() -> Tuple[float, float]:
    config_path = pathlib.Path(EXCHANGE_CONFIG_PATH)
    if config_path.exists():
        with config_path.open("r") as config:
            config = json.load(config)
        if not __validate_configuration(config_path, config):
            raise Exception("configuration failed validation: %s" % config_path.resolve())
        return config["Instrument"]["EtfClamp"], config["Instrument"]["TickSize"]
    return DEFAULT_ETF_CLAMP, DEFAULT_TICK_SIZE


def __show_splash() -> QtWidgets.QSplashScreen:
    splash = QtWidgets.QSplashScreen(QtGui.QPixmap(str(HERE.joinpath("images/splash.png"))))
    splash.show()
    return splash


def __show_main_window(splash: QtWidgets.QSplashScreen, event_source: EventSource) -> MainWindow:
    splash.showMessage("Creating main window...", Qt.AlignBottom, QtGui.QColor("#F0F0F0"))
    icon = QtGui.QIcon(str(HERE.joinpath("images/icon.png")))
    window = MainWindow(icon, event_source)
    window.show()
    splash.finish(window)
    return window


def __validate_configuration(filename: pathlib.Path, config: Mapping[str, Any]) -> bool:
    if type(config) is not dict:
        print("%s: expected JSON object got %s" % (filename, type(config).__name__), file=sys.stderr)
        return False

    if "Instrument" not in config:
        print("%s: missing Instrument section", file=sys.stderr)
        return False

    instrument = config["Instrument"]
    for key in ("EtfClamp", "TickSize"):
        if key not in instrument:
            print("%s: missing '%s' element in Instrument section" % (filename, key), file=sys.stderr)
            return False

        if type(instrument[key]) is not float:
            print("%s: expected float got %s" % (key, type(instrument[key]).__name__), file=sys.stderr)
            return False

    return True


def replay(path: pathlib.Path):
    app = __create_application()
    splash = __show_splash()
    splash.showMessage("Processing %s..." % str(path), Qt.AlignBottom, QtGui.QColor("#F0F0F0"))
    etf_clamp, tick_size = __read_exchange_config()
    with path.open("r", newline="") as csv_file:
        event_source = RecordedEventSource.from_csv(csv_file, etf_clamp, tick_size)
    window = __show_main_window(splash, event_source)
    return app.exec_()


def main(host: str, port: int):
    app = __create_application()
    splash = __show_splash()
    etf_clamp, tick_size = __read_exchange_config()
    time.sleep(1)
    event_source = LiveEventSource(host, port, etf_clamp, tick_size)
    window = __show_main_window(splash, event_source)
    return app.exec_()
