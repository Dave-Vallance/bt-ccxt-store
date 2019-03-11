import sys
import time

from backtrader import Cerebro, bt

from ccxtbt import CCXTStore


def main(strategy):
    cerebro = Cerebro(preload=False)

    cerebro.addstrategy(strategy)

    config = {
        'enableRateLimit': True,
        'nonce': lambda: str(int(time.time() * 1000)),
    }

    store = CCXTStore(
        exchange='binance',
        currency='BNB',
        config=config,
        retries=5,
        debug=True)

    broker = store.getbroker()
    cerebro.setbroker(broker)

    # Get our data
    # Drop newest will prevent us from loading partial data from incomplete candles
    data = store.getdata(exchange='binance',
                         dataname='BNB/USDT',
                         timeframe=bt.TimeFrame.Minutes,
                         fromdate=None,
                         compression=1,
                         ohlcv_limit=2,  # required to make calls to binance exchange work
                         currency='BNB',
                         config=config,
                         retries=5,
                         drop_newest=False,
                         # historical=True,
                         backfill_start=False,
                         backfill=False
                         # debug=True,
                         )
    # Add the feed
    cerebro.adddata(data)

    # Run the strategy
    return cerebro.run()


if __name__ == '__main__':
    sys_args = sys.argv[1:]
    main(sys_args)
