# Ready Trader Go

## IT'S READY TRADER GO TIME

Welcome to the ultimate team student trading competition. Competitors get to
learn all the fundamentals of trading and truly test their coding and analytical
skills. The aim is to build and optimise a trading algorithm that outperforms
all others on a virtual exchange.

To learn more about the competition, visit [readytradergo.optiver.com]
(https://readytradergo.optiver.com).

## Getting started

To run Ready Trader Go, you'll need Python version 3.11 or above and PySide6.
You can download Python from [www.python.org](https://www.python.org).

Once you have installed Python, you'll need to create a Python virtual
environment, and you can find instructions for creating and using virtual
environments at
[docs.python.org/3/library/venv.html](https://docs.python.org/3/library/venv.html).

To use the Ready Trader Go graphical user interface, you'll need to install
the [PySide6 package](https://pypi.org/project/PySide6/) which you can do by
running

```shell
pip3 install PySide6
```

in your Python virtual environment.

### Running a Ready Trader Go match

To run a Ready Trader Go match with one or more autotraders, simply run:

```shell
python3 rtg.py run [AUTOTRADER FILENAME [AUTOTRADER FILENAME]]
```

For example:

```shell
python3 rtg.py run autotrader.py
```

Each autotrader must have a corresponding JSON configuration file as described below.

## What's in this archive?

This archive contains everything needed to run a Ready Trader Go *match*
in which multiple autotraders compete against each other in a simulated
market. For the exact definition of a match, see the competition terms and
conditions.

The archive contains:

* autotrader.json - configuration file for an example autotrader
* autotrader.py - an example autotrader
* data - sample market data to use for testing
* exchange.json - configuration file for the exchange simulator
* ready_trader_go - the Ready Trader Go source code
* rtg.py - Use this with Python to run Ready Trader Go 

### Autotrader configuration

Each autotrader is configured with a JSON file like this:

    {
      "Execution": {
        "Host": "127.0.0.1",
        "Port": 12345
      },
      "Information": {
        "Type": "mmap",
        "Name": "info.dat"
      },
      "TeamName": "TraderOne",
      "Secret": "secret"
    }

The elements of the autotrader configuration are:

* Execution - network address for sending execution requests (e.g. to place
an order)
* Information - details of a memory-mapped file for information messages broadcast
by the exchange simulator
* TeamName - name of the team for this autotrader (each autotrader in a match
  must have a unique name)
* Secret - password for this autotrader

### Simulator configuration

The market simulator is configured with a JSON file called "exchange.json".
Here is an example:

    {
      "Engine": {
        "MarketDataFile": "data/market_data.csv",
        "MarketEventInterval": 0.05,
        "MarketOpenDelay": 5.0,
        "MatchEventsFile": "match_events.csv",
        "ScoreBoardFile": "score_board.csv",
        "Speed": 1.0,
        "TickInterval": 0.25
      },
      "Execution": {
        "host": "127.0.0.1",
        "Port": 12345
      },
      "Fees": {
        "Maker": -0.0001,
        "Taker": 0.0002
      },
      "Information": {
        "Type": "mmap",
        "Name": "info.dat"
      },
      "Instrument": {
        "EtfClamp": 0.002,
        "TickSize": 1.00
      },
      "Limits": {
        "ActiveOrderCountLimit": 10,
        "ActiveVolumeLimit": 200,
        "MessageFrequencyInterval": 1.0,
        "MessageFrequencyLimit": 50,
        "PositionLimit": 100
      },
      "Traders": {
        "TraderOne": "secret",
        "ExampleOne": "qwerty",
        "ExampleTwo": "12345"
      }
    }

The elements of the autotrader configuration are:

* Engine - source data file, output filename, simulation speed and tick interval
* Execution - network address to listen for autotrader connections
* Fees - details of the fee structure
* Information - details of a memory-mapped file used to broadcast information
messages to autotraders
* Instrument - details of the instrument to be traded
* Limits - details of the limits by which autotraders must abide
* Traders - team names and secrets of the autotraders

**Important:** Each autotrader must have a unique team name and password
listed in the 'Traders' section of the `exchange.json` file.

## The Ready Trader Go command line utility

The Ready Trader Go command line utility, `rtg.py`, can be used to run or
replay a match. For help, run:

```shell
python3 rtg.py --help
```

### Running a match

To run a match, use the "run" command and specify the autotraders you
wish to participate in the match:

```shell
python3 rtg.py run [AUTOTRADER FILENAME [AUTOTRADER FILENAME]]
```

Each autotrader must have a corresponding JSON file (with the same filename,
but ending in ".json" instead of ".py") which contains a unique team name
and the team name and secret must be listed in the `exchange.json` file.

It will take approximately 60 minutes for the match to complete and several
files will be produced:

* `autotrader.log` - log file for an autotrader
* `exchange.log` - log file for the simulator
* `match_events.csv` - a record of events during the match
* `score_board.csv` - a record of each autotrader's score over time

To aid testing, you can speed up the match by modifying the "Speed" setting
in the "exchange.json" configuration file - for example, setting the speed
to 2.0 will halve the time it takes to run a match. Note, however, that
increasing the speed may change the results.

When testing your autotrader, you should try it with different sample data
files by modifying the "MarketDataFile" setting in the "exchange.json"
file.

### Replaying a match

To replay a match, use the "replay" command and specify the name of the
match events file you wish to replay:

```shell
python3 rtg.py replay match_events.csv
```

### Autotrader environment

Autotraders in Ready Trader Go will be run in the following environment:

* Operating system: Linux
* Python version: 3.11.2
* Available libraries: numpy 1.24.2; pandas 1.5.3; scipy 1.10.1
* Memory limit: 2GB
* Total disk usage limit: 100MB (including the log file)
* Maximum number of autotraders per match: 8
* Autotraders may not create sub-processes but may have multiple threads
* Autotraders may not access the internet

## How do I submit my AutoTrader?

Shortly after the competition begins you'll be supplied with the details of
a [GIT repository](https://git-scm.com) which you can use to submit your
autotrader. To access the GIT repository, you'll first need to 'clone' it.

For example:

```shell
git clone https://git-codecommit.eu-central-1.amazonaws.com/v1/repos/TEAM_NAME
```

(replace 'TEAM_NAME' with your team name.)

To submit your autotrader, you need to _commit_ your `autotrader.py` file to the
GIT repository and then _push_ that commit to your Git repository. For example:

```shell
git add autotrader.py
git commit -m "Updating my autotrader"
git push
```

Do _not_ put the `autotrader.py` file in a folder and do _not_ include any other
files (any other files will be ignored). You may only submit one autotrader (i.e.
you cannot submit both a Python and a C++ autotrader). 

You may replace your autotrader with a new one at any time. When each
tournament starts we'll use the autotrader in your GIT repository at the
cut-off time for that tournament.
