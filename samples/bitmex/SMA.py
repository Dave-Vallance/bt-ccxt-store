from ccxtbt import CCXTStore
import backtrader as bt
from datetime import datetime, timedelta
import json

class TestStrategy(bt.Strategy):

    def __init__(self):

        self.sma = bt.indicators.SMA(self.data,period=21)

    def next(self):

        # Get cash and balance
        # New broker method that will let you get the cash and balance for
        # any wallet. It also means we can disable the getcash() and getvalue()
        # rest calls before and after next which slows things down.

        # NOTE: If you try to get the wallet balance from a wallet you have
        # never funded, a KeyError will be raised! Change LTC below as approriate
        if self.live_data:
            cash, value = self.broker.get_wallet_balance('BTC')
        else:
            # Avoid checking the balance during a backfill. Otherwise, it will
            # Slow things down.
            cash = 'NA'

        for data in self.datas:

            print('{} - {} | Cash {} | O: {} H: {} L: {} C: {} V:{} SMA:{}'.format(data.datetime.datetime(),
                                                                                   data._name, cash, data.open[0], data.high[0], data.low[0], data.close[0], data.volume[0],
                                                                                   self.sma[0]))

    def notify_data(self, data, status, *args, **kwargs):
        dn = data._name
        dt = datetime.now()
        msg= 'Data Status: {}'.format(data._getstatusname(status))
        print(dt,dn,msg)
        if data._getstatusname(status) == 'LIVE':
            self.live_data = True
        else:
            self.live_data = False

with open('./samples/params.json', 'r') as f:
    params = json.load(f)

cerebro = bt.Cerebro(quicknotify=True)


# Add the strategy
cerebro.addstrategy(TestStrategy)

# Create our store
config = {'apiKey': params["bitmex"]["apikey"],
          'secret': params["bitmex"]["secret"],
          'enableRateLimit': True,
          }


# IMPORTANT NOTE - To use the testnet on Bitmex you need to register and 
# create an API key on http://testnet.bitmex.com
store = CCXTStore(exchange='bitmex', currency='BTC', config=config, retries=5, debug=False, sandbox=True)


# Get the broker and pass any kwargs if needed.
# ----------------------------------------------
# Broker mappings have been added since some exchanges expect different values
# to the defaults. Case in point, Kraken vs Bitmex. NOTE: Broker mappings are not
# required if the broker uses the same values as the defaults in CCXTBroker.
broker_mapping = {
    'order_types': {
        bt.Order.Market: 'market',
        bt.Order.Limit: 'limit',
        bt.Order.Stop: 'stop',
        bt.Order.StopLimit: 'stop limit'
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
data = store.getdata(dataname='ETH/USD', name="ETHUSD",
                     timeframe=bt.TimeFrame.Minutes, fromdate=hist_start_date,
                     compression=1, ohlcv_limit=50, drop_newest=True) #, historical=True)

# Add the feed
cerebro.adddata(data)

# Run the strategy
cerebro.run()