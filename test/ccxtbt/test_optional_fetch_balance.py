import time
import unittest
from datetime import datetime
from unittest.mock import patch

from backtrader import Strategy, Cerebro, TimeFrame

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
    ohlcv data to try out this lib.
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

    @patch('ccxt.binance.fetch_balance')
    def test_fetch_balance_throws_error(self, fetch_balance_mock):
        """
        If API keys are provided the store is expected to fetch the balance.
        """

        config = {
            'apikey': 'an-api-key',
            'secret': 'an-api-secret',
            'enableRateLimit': True,
            'nonce': lambda: str(int(time.time() * 1000))
        }
        backtesting(config)

        fetch_balance_mock.assert_called_once()

    def test_default_fetch_balance_param(self):
        """
        If API keys are provided the store is expected to
        not fetch the balance and load the ohlcv data without them.
        """
        config = {
            'enableRateLimit': True,
            'nonce': lambda: str(int(time.time() * 1000))
        }
        finished_strategies = backtesting(config)
        self.assertEqual(finished_strategies[0].next_runs, 3)


class TestStrategy(Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        print('%s closing price: %s' % (dt.isoformat(), self.datas[0].close[0]))
        self.next_runs += 1


def backtesting(config):
    cerebro = Cerebro()

    cerebro.addstrategy(TestStrategy)

    cerebro.adddata(CCXTFeed(exchange='binance',
                             dataname='BNB/USDT',
                             timeframe=TimeFrame.Minutes,
                             fromdate=datetime(2019, 1, 1, 0, 0),
                             todate=datetime(2019, 1, 1, 0, 2),
                             compression=1,
                             ohlcv_limit=2,
                             currency='BNB',
                             config=config,
                             retries=5))

    finished_strategies = cerebro.run()
    return finished_strategies


if __name__ == '__main__':
    unittest.main()
