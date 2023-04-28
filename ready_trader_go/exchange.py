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
import socket

from .account import AccountFactory
from .application import Application
from .competitor import CompetitorManager
from .controller import Controller
from .execution import ExecutionServer
from .heads_up import HeadsUpDisplayServer
from .information import InformationPublisher
from .limiter import FrequencyLimiterFactory
from .market_events import MarketEventsReader
from .match_events import MatchEvents, MatchEventsWriter
from .order_book import OrderBook
from .pubsub import PublisherFactory
from .score_board import ScoreBoardWriter
from .timer import Timer
from .types import Instrument
from .unhedged_lots import UnhedgedLotsFactory


def __validate_hostname(config, section, key):
    try:
        config[section][key] = socket.gethostbyname(config[section][key])
    except socket.error:
        raise Exception("Could not validate hostname in %s.%s configuration" % (section, key))


def __validate_object(config, section, required_keys, value_types):
    obj = config[section]
    if type(obj) is not dict:
        raise Exception("%s configuration should be a JSON object" % section)
    if any(k not in obj for k in required_keys):
        raise Exception("A required key is missing from the %s configuration" % section)
    if any(type(obj[k]) is not t for k, t in zip(required_keys, value_types)):
        raise Exception("Element of inappropriate type in %s configuration" % section)


def __exchange_config_validator(config):
    """Return True if the specified config is valid, otherwise raise an exception."""
    if type(config) is not dict:
        raise Exception("Configuration file contents should be a JSON object")
    if any(k not in config for k in ("Engine", "Execution", "Fees", "Information", "Instrument", "Limits", "Traders")):
        raise Exception("A required key is missing from the configuration")

    __validate_object(config, "Engine", ("MarketDataFile", "MarketEventInterval", "MarketOpenDelay", "MatchEventsFile",
                                         "ScoreBoardFile", "Speed", "TickInterval"),
                      (str, float, float, str, str, float, float))
    __validate_object(config, "Execution", ("Host", "Port"), (str, int))
    __validate_object(config, "Fees", ("Maker", "Taker"), (float, float))
    __validate_object(config, "Information", ("Type", "Name"), (str, str))
    __validate_object(config, "Instrument", ("EtfClamp", "TickSize",), (float, float))
    __validate_object(config, "Limits", ("ActiveOrderCountLimit", "ActiveVolumeLimit", "MessageFrequencyInterval",
                                         "MessageFrequencyLimit", "PositionLimit"), (int, int, float, int, int))
    __validate_hostname(config, "Execution", "Host")

    if "Hud" in config:
        __validate_object(config, "Hud", ("Host", "Port"), (str, int))
        __validate_hostname(config, "Hud", "Host")

    if type(config["Traders"]) is not dict:
        raise Exception("Traders configuration should be a JSON object")
    if any(type(k) is not str for k in config["Traders"]):
        raise Exception("Key of inappropriate type in Traders configuration")
    if any(type(v) is not str for v in config["Traders"].values()):
        raise Exception("Element of inappropriate type in Traders configuration")

    return True


def setup(app: Application) -> Controller:
    """Setup the exchange simulator."""
    engine = app.config["Engine"]
    exec_ = app.config["Execution"]
    info = app.config["Information"]
    instrument = app.config["Instrument"]
    limits = app.config["Limits"]

    future_book = OrderBook(Instrument.FUTURE, 0.0, 0.0)
    etf_book = OrderBook(Instrument.ETF, app.config["Fees"]["Maker"], app.config["Fees"]["Taker"])

    match_events = MatchEvents()
    match_events_writer = MatchEventsWriter(match_events, engine["MatchEventsFile"], app.event_loop)
    market_events_reader = MarketEventsReader(engine["MarketDataFile"], app.event_loop, future_book, etf_book,
                                              match_events)
    score_board_writer = ScoreBoardWriter(engine["ScoreBoardFile"], app.event_loop)

    tick_timer = Timer(engine["TickInterval"], engine["Speed"])
    account_factory = AccountFactory(instrument["EtfClamp"], instrument["TickSize"])
    unhedged_lots_factory = UnhedgedLotsFactory()
    competitor_manager = CompetitorManager(app.config["Limits"], app.config["Traders"], account_factory, etf_book,
                                           future_book, match_events, score_board_writer, instrument["TickSize"],
                                           tick_timer, unhedged_lots_factory)

    limiter_factory = FrequencyLimiterFactory(limits["MessageFrequencyInterval"] / engine["Speed"],
                                              limits["MessageFrequencyLimit"])
    exec_server = ExecutionServer(exec_["Host"], exec_["Port"], competitor_manager, limiter_factory)
    info_publisher = InformationPublisher(app.event_loop, PublisherFactory(info["Type"], info["Name"]),
                                          (future_book, etf_book), tick_timer)

    market_timer = Timer(engine["MarketEventInterval"], engine["Speed"])
    controller = Controller(engine["MarketOpenDelay"], exec_server, info_publisher, market_events_reader,
                            match_events_writer, score_board_writer, market_timer, tick_timer)
    competitor_manager.controller = controller
    exec_server.controller = controller

    if "Hud" in app.config:
        hud_server = HeadsUpDisplayServer(app.config["Hud"]["Host"], app.config["Hud"]["Port"], match_events,
                                          competitor_manager, controller)
        controller.heads_up_display_server = hud_server

    app.event_loop.create_task(controller.start())
    return controller


def main():
    app = Application("exchange", __exchange_config_validator)
    controller: Controller = setup(app)
    app.run()
    controller.cleanup()
