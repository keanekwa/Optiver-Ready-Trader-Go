# Optiver-Ready-Trader-Go

<img width="500" alt="image" src="https://user-images.githubusercontent.com/8297863/235014898-e37b28aa-d479-42ce-b6c2-c60dc18c9e7d.png">

## How the Competition Works

This repository documents our submission for the [Optiver Ready Trader Go](https://readytradergo.optiver.com/) competition. This competition involves creating a algorithmic trading strategy to trade a Future and ETF, both of which are highly correlated.

<img width="614" alt="image" src="https://user-images.githubusercontent.com/8297863/235014377-92f87103-6bfa-456d-9ef8-f0d3ea3f20f2.png">

The Future was highly liquid, while the ETF was highly illiquid.

<img width="574" alt="image" src="https://user-images.githubusercontent.com/8297863/235014437-95749871-a6e3-42e7-9233-6982be55db20.png">

We were also provided with some basic template files (refer to the /ready_trader_go folder) and some market data for backtesting (refer to the /market_data folder) to interface with the trading system, and we had to follow these [competition rules](https://readytradergo.optiver.com/how-to-play/).

## Models We Tried

We tried out a variety of different strategies including:
1. Avellaneda-Stoikov Market Making Model
2. Arbitrage strategy between the ETF and Future, whereby we bought the underpriced instrument and sold the overpriced instrument
3. Arbitrage strategy that took into account the momentum of the prices (e.g. if both the ETF and Future prices are going up, buy more of the underpriced instrument, and sell a smaller quantity of the overpriced instrument)
4. Mid-price trader
5. Mid-price trader with adjustment for current inventory levels

From extensive testing, we concluded that the Avellaneda-Stoikov Market Making Model was the most reliable model across different market conditions.

## Avellaneda-Stoikov Market Making Model

This model works by finding an optimal reservation price (i.e. fair price we wish to trade our instrument), and optimal bid-ask spread (i.e. how wide of a spread we wish to market make).

<img width="690" alt="image" src="https://user-images.githubusercontent.com/8297863/235012352-8d091bc7-5d1e-404c-891f-37c1f7b6a381.png">

## How to Run the Model(s)

You'll need Python version 3.11 or above and [PySide6](https://pypi.org/project/PySide6/) for the GUI. To install PySide6, you can run:
```
pip3 install PySide6
```

Afterwards, you can run the different autotrader algorithms against each other by running:
```
python3 rtg.py run [AUTOTRADER FILENAME [AUTOTRADER FILENAME]]
```

For example, this is how to run the Avellaneda-Stoikov model alone:
```
python3 rtg.py run ASModel.py
```

And this is how to run all the models to see how they compare:
```
python3 rtg.py run ASModel.py arbitrage.py momentumArbitrage.py midtrader.py midtraderInvAdj.py 
```

To backtest against different market data, update the "MarketDataFile" attribute in the exchange.json file. To increase the speed of backtesting, adjust the "Speed" attribute.

<img width="330" alt="image" src="https://user-images.githubusercontent.com/8297863/235015806-e11980ac-cace-42a4-9856-efe1a2ffded9.png">

## References
- [Avellaneda M. & Stoikov S. (2006). High Frequency Trading in a Limit Order Book](https://www.researchgate.net/publication/24086205_High_Frequency_Trading_in_a_Limit_Order_Book)
- [Hummingbot Foundation. (2021). A comprehensive guide to Avellaneda & Stoikov’s market-making strategy](https://blog.hummingbot.org/2021-04-avellaneda-stoikov-market-making-strategy/)
