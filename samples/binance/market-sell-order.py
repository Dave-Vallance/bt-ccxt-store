import json
import os
import time
from datetime import datetime, timedelta

import backtrader as bt

from ccxtbt import CCXTStore


class TestStrategy(bt.Strategy):

    def __init__(self):

        self.bought = False
        # To keep track of pending orders and buy price/commission
        self.order = None

    def next(self):

        if self.live_data and not self.bought:
            # Market Sell
            # size x market price should be >10 USDT at a minimum at Binance
            # Attention: This will make an actual trade!
            self.order = self.sell(size=1.0)
            self.bought = True

        for data in self.datas:
            print('{} - {} | O: {} H: {} L: {} C: {} V:{}'.format(data.datetime.datetime(),
                                                                  data._name, data.open[0], data.high[0], data.low[0],
                                                                  data.close[0], data.volume[0]))

    def notify_data(self, data, status, *args, **kwargs):
        dn = data._name
        dt = datetime.now()
        msg = 'Data Status: {}, Order Status: {}'.format(data._getstatusname(status), status)
        print(dt, dn, msg)
        if data._getstatusname(status) == 'LIVE':
            self.live_data = True
        else:
            self.live_data = False


# absolute dir the script is in
script_dir = os.path.dirname(__file__)
abs_file_path = os.path.join(script_dir, '../params.json')
with open(abs_file_path, 'r') as f:
    params = json.load(f)

cerebro = bt.Cerebro(quicknotify=True)

# Add the strategy
cerebro.addstrategy(TestStrategy)

# Create our store
config = {'apiKey': params["binance"]["apikey"],
          'secret': params["binance"]["secret"],
          'enableRateLimit': True,
          'nonce': lambda: str(int(time.time() * 1000)),
          }

store = CCXTStore(exchange='binance', currency='BNB', config=config, retries=5, debug=True)

cerebro.setbroker(store.getbroker())

# Get our data
# Drop newest will prevent us from loading partial data from incomplete candles
hist_start_date = datetime.utcnow() - timedelta(minutes=50)
data = store.getdata(dataname='BNB/USDT', name="BNBUSDT",
                     timeframe=bt.TimeFrame.Minutes, fromdate=hist_start_date,
                     compression=1, ohlcv_limit=50, drop_newest=True)  # , historical=True)

# Add the feed
cerebro.adddata(data)

# Run the strategy
cerebro.run()
