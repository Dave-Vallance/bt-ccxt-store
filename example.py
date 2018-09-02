from ccxtbt import CCXTStore
import backtrader as bt
from datetime import datetime, timedelta


class TestStrategy(bt.Strategy):

    def __init__(self):

        self.sma = bt.indicators.SMA(self.data,period=21)

    def next(self):

        for data in self.datas:

            print('{} - {} | O: {} H: {} L: {} C: {} V:{} SMA:{}'.format(data.datetime.datetime(),
                data._name, data.open[0], data.high[0], data.low[0], data.close[0], data.volume[0],
                self.sma[0]))

    def notify_data(self, data, status, *args, **kwargs):
        dn = data._name
        dt = datetime.now()
        msg= 'Data Status: {}'.format(data._getstatusname(status))
        print(dt,dn,msg)

        # This bit will allow you to backfill faster when starting the script
        # Use with care as it is a hacky workaround and will stop making rest
        # calls to get cash and value until a live notification is received.
        if data._getstatusname(status) == 'DELAYED':
            self.broker.balance_checks = False

        if data._getstatusname(status) == 'LIVE':
            self.broker.balance_checks = True



apikey = 'Insert Your API Key'
secret = 'Insert Your Secret'

cerebro = bt.Cerebro(quicknotify=True)


# Add the strategy
cerebro.addstrategy(TestStrategy)

# Create our store
config = {'apiKey': apikey,
            'secret': secret,
            'enableRateLimit': True
            }

# IMPORTANT NOTE - Kraken (and some other exchanges) will not return any values
# for get cash or value if You have never held any LTC coins in your account.
# So switch LTC to a coin you have funded previously if you get errors
store = CCXTStore(exchange='kraken', currency='LTC', config=config, retries=5, debug=False)


# Get the broker and pass any kwargs if needed.
# ----------------------------------------------
# Broker mappings have been added since some exchanges expect different values
# to the defaults. Case in point, Kraken vs Bitmex. Broker mappings are not required
# if the broker uses the same values as the defaults in CCXTBroker.
broker_mapping = {
    'order_types': {
        bt.Order.Market: 'market',
        bt.Order.Limit: 'limit',
        bt.Order.Stop: 'stop-loss', #stop-loss for kraken, stop for bitmex
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
hist_start_date = datetime.utcnow() - timedelta(minutes=50)
data = store.getdata(dataname='LTC/USD', name="LTF",
                         timeframe=bt.TimeFrame.Minutes, fromdate=hist_start_date,
                         compression=1, ohlcv_limit=50) #, historical=True)

# Add the feed
cerebro.adddata(data)

# Run the strategy
cerebro.run()
