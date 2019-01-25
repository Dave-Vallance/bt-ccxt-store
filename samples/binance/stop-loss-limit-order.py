import os

from ccxtbt import CCXTStore
from backtrader import Order
import backtrader as bt
from datetime import datetime, timedelta
import time
import json
import logging

class TestStrategy(bt.Strategy):

    def __init__(self):

        logging.basicConfig(level=logging.DEBUG)
        self.sold = False
        # To keep track of pending orders and buy price/commission
        self.order = None

    def next(self):

        if self.live_data and not self.sold:

            # In this configuration the StopLimit order of Backtrader is mapped to "STOP_LOSS_LIMIT" from Binance
            # With that order type Binance requires the stopPrice to be below the current market price
            # see https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#new-order--trade
            # "Trigger order price rules against market price for both MARKET and LIMIT versions:"
            #
            # Attention! If you don't want to actually sell the stopPrice should be way below the market price.
            # This way you still have time to cancel the order at the exchange.
            self.order = self.sell(size=2.0, exectype=Order.StopLimit, price=5.475, stopPrice=5.4763)
            self.sold = True

        for data in self.datas:

            print('{} - {} | O: {} H: {} L: {} C: {} V:{}'.format(data.datetime.datetime(),
                                                                                   data._name, data.open[0], data.high[0], data.low[0], data.close[0], data.volume[0]))

    def notify_data(self, data, status, *args, **kwargs):
        dn = data._name
        dt = datetime.now()
        msg= 'Data Status: {}, Order Status: {}'.format(data._getstatusname(status), status)
        print(dt,dn,msg)
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

cerebro.broker.setcash(10.0)

# Add the strategy
cerebro.addstrategy(TestStrategy)

# Create our store
config = {'apiKey': params["binance"]["apikey"],
          'secret': params["binance"]["secret"],
          'enableRateLimit': True,
          'nonce': lambda: str(int(time.time() * 1000)),
          }

store = CCXTStore(exchange='binance', currency='BNB', config=config, retries=5, debug=True)


# Get the broker and pass any kwargs if needed.
# ----------------------------------------------
# Broker mappings have been added since some exchanges expect different values
# to the defaults. Case in point, Kraken vs Bitmex. NOTE: Broker mappings are not
# required if the broker uses the same values as the defaults in CCXTBroker.
broker_mapping = {
    'order_types': {
        bt.Order.Market: 'market',
        bt.Order.Limit: 'limit',
        bt.Order.Stop: 'stop_loss', #stop-loss for kraken, stop for bitmex
        bt.Order.StopLimit: 'STOP_LOSS_LIMIT'
    },
    'mappings':{
        'closed_order':{
            'key': 'status',
            'value':'closed'
        },
        'canceled_order':{
            'key': 'result',
            'value':1}
    }
}

broker = store.getbroker(broker_mapping=broker_mapping)
cerebro.setbroker(broker)

# Get our data
# Drop newest will prevent us from loading partial data from incomplete candles
hist_start_date = datetime.utcnow() - timedelta(minutes=50)
data = store.getdata(dataname='BNB/USDT', name="BNBUSDT",
                     timeframe=bt.TimeFrame.Minutes, fromdate=hist_start_date,
                     compression=1, ohlcv_limit=50, drop_newest=True) #, historical=True)

# Add the feed
cerebro.adddata(data)

# Run the strategy
cerebro.run()