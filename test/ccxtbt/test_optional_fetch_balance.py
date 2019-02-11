import time
import unittest
from datetime import datetime

from backtrader import Strategy, Cerebro, TimeFrame
from ccxt import AuthenticationError

from ccxtbt import CCXTFeed, CCXTStore


class TestFeedInitialFetchBalance(unittest.TestCase):
    """
    At least at Binance and probably on other exchanges too fetching ohlcv data doesn't need authentication
    while obviously fetching the balance of ones account does need authentication.
    Usually the CCXTStore fetches the balance when it is initialized which is not a problem during live trading
    operation.
    But the store is also initialized when the CCXTFeed is created and used during unit testing and backtesting.
    For this case it is beneficial to turn off the initial fetching of the balance as it is not really needed and
    it avoids needing to have api keys.
    This makes it possible for users that don't have a Binance api key to run backtesting and unit tests with real
    ohlcv data.
    """

    def setUp(self):
        """
        The initial balance is fetched in the context of the initialization of the CCXTStore.
        But as the CCXTStore is a singleton it's normally initialized only once and the instance is reused
        causing side effects.
        If the  first test run initializes the store without fetching the balance a subsequent test run
        would not try to fetch the balance again as the initialization won't happen again.
        Resetting the singleton to None here causes the initialization of the store to happen in every test method.
        """
        CCXTStore._singleton = None

    def test_fetch_balance_throws_error(self):
        """
        If no parameter is provided to `CCXTFeed()` it should assume
        if `initially_fetch_balance` is set to `True` in the `CCXTFeed`
        it is expected to throw an Authentication error if no credentials
        are provided.
        """
        self.assertRaises(AuthenticationError, backtesting, initially_fetch_balance=True)

    def test_without_fetch_balance(self):
        """
        If `initially_fetch_balance=False` then `CCXTFeed` should instruct
        the store not to initially fetch the balance.
        This is expected to should just load the data
        and not throw an Authentication error.
        """
        finished_strategies = backtesting(initially_fetch_balance=False)
        self.assertEqual(finished_strategies[0].next_runs, 3)

    def test_default_fetch_balance_param(self):
        """
        If no parameter is provided to `CCXTFeed()` it should assume
        `initially_fetch_balance=False` and not throw an error.
        Instead it should just load the data.
        """
        finished_strategies = backtesting()
        self.assertEqual(finished_strategies[0].next_runs, 3)


class TestStrategy(Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        print('%s closing price: %s' % (dt.isoformat(), self.datas[0].close[0]))
        self.next_runs += 1


def backtesting(initially_fetch_balance=None):
    cerebro = Cerebro()

    cerebro.addstrategy(TestStrategy)

    # 'apiKey' and 'secret' are skipped
    config = {'enableRateLimit': True, 'nonce': lambda: str(int(time.time() * 1000))}

    feed_params = dict(exchange='binance',
                       dataname='BNB/USDT',
                       timeframe=TimeFrame.Minutes,
                       fromdate=datetime(2019, 1, 1, 0, 0),
                       todate=datetime(2019, 1, 1, 0, 2),
                       compression=1,
                       ohlcv_limit=2,
                       currency='BNB',
                       config=config,
                       retries=5)
    if initially_fetch_balance:
        feed_params['initially_fetch_balance'] = initially_fetch_balance

    feed = CCXTFeed(**feed_params)
    cerebro.adddata(feed)

    finished_strategies = cerebro.run()
    return finished_strategies


if __name__ == '__main__':
    unittest.main()
