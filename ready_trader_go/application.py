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
import json
import logging
import pathlib
import signal
import sys

from typing import Callable, Optional


class Application(object):
    """Standard application setup."""

    def __init__(self, name: str, config_validator: Optional[Callable] = None):
        """Initialise a new instance of the Application class."""
        self.event_loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self.logger = logging.getLogger("APP")
        self.name: str = name

        # Turn on debugging if you're having trouble with the event loop
        # self.event_loop.set_debug(True)

        try:
            self.event_loop.add_signal_handler(signal.SIGINT, self.on_signal, signal.SIGINT)
            self.event_loop.add_signal_handler(signal.SIGTERM, self.on_signal, signal.SIGTERM)
        except NotImplementedError:
            # Signal handlers are only implemented on Unix
            pass

        self.config = None
        config_path = pathlib.Path(name + ".json")
        if config_path.exists():
            with config_path.open("r") as config:
                self.config = json.load(config)
            if config_validator is not None and not config_validator(self.config):
                raise Exception("configuration failed validation: %s" % config_path.resolve())
        elif config_validator is not None:
            raise Exception("configuration file does not exist: %s" % str(config_path))

        logging.basicConfig(filename=f'{name}.log', format="%(asctime)s [%(levelname)-7s] [%(name)s] %(message)s",
                            level=logging.INFO)

        self.logger.info("%s started with arguments={%s}", self.name, ", ".join(sys.argv))
        if self.config is not None:
            self.logger.info("configuration=%s", json.dumps(self.config, separators=(',', ':')))

    def on_signal(self, signum: int) -> None:
        """Called when a signal is received."""
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        self.logger.info("%s signal received - shutting down...", sig_name)
        self.event_loop.stop()

    def run(self) -> None:
        """Start the application's event loop."""
        loop = self.event_loop

        try:
            loop.run_forever()
        except Exception as e:
            self.logger.error("application raised an exception:", exc_info=e)
            raise
        finally:
            self.logger.info("closing event loop")
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()
