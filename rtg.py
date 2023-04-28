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
import argparse
import multiprocessing
import pathlib
import subprocess
import sys
import time
import traceback

import ready_trader_go.exchange
import ready_trader_go.trader

try:
    from ready_trader_go.hud.__main__ import main as hud_main, replay as hud_replay
except ImportError:
    hud_main = hud_replay = None


def no_heads_up_display() -> None:
    print("Cannot run the Ready Trader Go heads-up display. This could\n"
          "mean that the PySide6 module has not been installed. Please\n"
          "see the README.md file for more information.", file=sys.stderr)


def replay(args) -> None:
    """Replay a match from a file."""
    if hud_replay is None:
        no_heads_up_display()
        return

    path: pathlib.Path = args.filename
    if not path.is_file():
        print("'%s' is not a regular file" % str(path), file=sys.stderr)
        return

    hud_replay(path)


def on_error(name: str, error: Exception) -> None:
    print("%s threw an exception: %s" % (name, error), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def run(args) -> None:
    """Run a match."""
    for auto_trader in args.autotrader:
        if auto_trader.suffix.lower == ".py" and auto_trader.parent != pathlib.Path("."):
            print("Python auto traders cannot be in a different directory: '%s'" % auto_trader, file=sys.stderr)
            return
        if not auto_trader.exists():
            print("'%s' does not exist" % auto_trader, file=sys.stderr)
            return
        if not auto_trader.with_suffix(".json").exists():
            print("'%s': configuration file is missing: %s" % (auto_trader, auto_trader.with_suffix(".json")))
            return

    with multiprocessing.Pool(len(args.autotrader) + 2, maxtasksperchild=1) as pool:
        exchange = pool.apply_async(ready_trader_go.exchange.main,
                                    error_callback=lambda e: on_error("The exchange simulator", e))

        # Give the exchange simulator a chance to start up.
        time.sleep(0.5)
        
        for path in args.autotrader:
            if path.suffix.lower() == ".py":
                pool.apply_async(ready_trader_go.trader.main, (path.with_suffix("").name,),
                                 error_callback=lambda e: on_error("Auto-trader '%s'" % path, e))
            else:
                resolved: pathlib.Path = path.resolve()
                pool.apply_async(subprocess.run, ([resolved],), {"check": True, "cwd": resolved.parent},
                                 error_callback=lambda e: on_error("Auto-trader '%s'" % path, e))

        if hud_main is None:
            no_heads_up_display()
            exchange.get()
        else:
            hud_main(args.host, args.port)


def main() -> None:
    """Process command line arguments and execute the given command."""
    parser = argparse.ArgumentParser(description="Ready Trader Go command line utility.")
    subparsers = parser.add_subparsers(title="command")

    run_parser = subparsers.add_parser("run", aliases=["go", "ru"],
                                       description="Run a Ready Trader Go match.",
                                       help="run a Ready Trader Go match")
    # On Mac OSX resolving the name 'localhost' can take forever, so be sure
    # to use '127.0.0.1' here.
    run_parser.add_argument("--host", default="127.0.0.1",
                            help="host name of the exchange simulator (default '127.0.0.1')")
    run_parser.add_argument("--port", default=12347,
                            help="port number of the exchange simulator (default 12347)")
    run_parser.add_argument("autotrader", nargs="*", type=pathlib.Path,
                            help="auto-traders to include in the match")
    run_parser.set_defaults(func=run)

    replay_parser = subparsers.add_parser("replay", aliases=["re"],
                                          description=("View a replay of a Ready Trader Go match from "
                                                       " a match events file."),
                                          help="replay a Ready Trader Go match from a file")
    replay_parser.add_argument("filename", nargs="?", default=pathlib.Path("match_events.csv"),
                               help="name of the match events file to replay (default 'match_events.csv')",
                               type=pathlib.Path)
    replay_parser.set_defaults(func=replay)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    if sys.platform == "darwin":
        multiprocessing.set_start_method("spawn")
    main()
