DEFAULT_DATE_TIME_FORMAT = "%d-%m-%y %H:%M"

# Credits: https://gist.github.com/rodrigo-brito/3b0fca2487c92ad97869247edd5fd852
import time
import backtrader as bt
import datetime as dt
from ccxtbt import CCXTStore

DEBUG = True


class CustomStrategy(bt.Strategy):
    def __init__(self):
        self.status = "DISCONNECTED"

    def notify_data(self, data, status, *args, **kwargs):
        self.status = data._getstatusname(status)
        if status == data.LIVE:
            self.log("LIVE DATA - Ready to trade")
        else:
            # INFO: At this moment of time, there is no data available yet. Hence there is no data.datetime.
            # If run self.log("NOT LIVE - {}".format(self.status)), will get IndexError: array index out of range
            print("[{}] NOT LIVE but {}".format(dt.datetime.utcnow().strftime(DEFAULT_DATE_TIME_FORMAT), self.status))

    def next(self):
        if self.status != "LIVE":
            self.log("{} - O: {:.8} C: {:.8}".format(self.status, self.data0.open[0], self.data0.close[0]))
            return

        self.log("{} - O: {:.8} C: {:.8}".format(self.status, self.data0.open[0], self.data0.close[0]))

    def log(self, txt):
        if not DEBUG:
            return

        dt = self.data0.datetime.datetime()
        print('[%s] %s' % (dt.strftime(DEFAULT_DATE_TIME_FORMAT), txt))


def main():
    BYBIT_EXCHANGE_ID = 'bybit'
    BYBIT_OHLCV_LIMIT = 200
    symbol_name = "BTC/USD"
    symbol_id = symbol_name.replace("/", "")
    currency = symbol_id[:-3]

    cerebro = bt.Cerebro(quicknotify=True)

    # Change to your API and SECRET
    broker_config = {
        'apiKey': api,
        'secret': secret,
        'nonce': lambda: str(int(time.time() * 1000)),
        'enableRateLimit': True,
    }

    store = CCXTStore(exchange=BYBIT_EXCHANGE_ID, currency=currency, config=broker_config, retries=5, debug=False,
                      sandbox=True)

    broker_mapping = {
        'order_types': {
            bt.Order.Market: 'market',
            bt.Order.Limit: 'limit',
            bt.Order.Stop: 'stop-loss',  # stop-loss for kraken, stop for bitmex
            bt.Order.StopLimit: 'stop limit'
        },
        'mappings': {
            'closed_order': {
                'key': 'status',
                'value': 'closed'
            },
            'canceled_order': {
                'key': 'result',
                'value': 1
            }
        }
    }

    broker = store.getbroker(broker_mapping=broker_mapping)
    cerebro.setbroker(broker)

    # Default value
    timeframe = None
    compression = None
    days = None
    hours = None
    minutes = None

    # Change the assignment based on your need
    # days = 1
    hours = 1
    # minutes = 15
    # minutes = 1

    if days is not None:
        timeframe = bt.TimeFrame.Days
        compression = days
        hist_start_date = dt.datetime.utcnow() - dt.timedelta(hours=days * 24 * BYBIT_OHLCV_LIMIT)
    elif hours is not None:
        timeframe = bt.TimeFrame.Minutes
        compression = hours * 60
        hist_start_date = dt.datetime.utcnow() - dt.timedelta(hours=hours * BYBIT_OHLCV_LIMIT)
    elif minutes is not None:
        timeframe = bt.TimeFrame.Minutes
        compression = minutes
        hist_start_date = dt.datetime.utcnow() - dt.timedelta(minutes=minutes * BYBIT_OHLCV_LIMIT)

    data = store.getdata(
        dataname=symbol_name,
        name=symbol_id,
        fromdate=hist_start_date,
        timeframe=timeframe,
        compression=compression,
        ohlcv_limit=BYBIT_OHLCV_LIMIT
    )

    cerebro.adddata(data)
    cerebro.addstrategy(CustomStrategy)
    cerebro.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        time = dt.datetime.utcnow().strftime(DEFAULT_DATE_TIME_FORMAT)
        print("[{}] finished by user.".format(time))
