import json
import unittest
from unittest.mock import patch, ANY

from backtrader import Strategy, Order

from ccxtbt import CCXTOrder
from test.ccxtbt.mapping import trading


class TestBinanceBroker(unittest.TestCase):
    """
    Tests all functionality supported by this broker.
    """

    def setUp(self):
        fetch_balance_patcher = patch('ccxt.binance.fetch_balance')
        fetch_balance_patcher.start()
        self.addCleanup(fetch_balance_patcher.stop)

        with open('./mock_balance.json', 'r') as f:
            mock_balance = json.load(f)
        fetch_balance_patcher.return_value = mock_balance

    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_limit_buy(self, binance_create_order_mock, fetch_order_mock):
        with open('./ccxt_order_result/limit/limit_buy.json', 'r') as f:
            buy_order_result = json.load(f)
        binance_create_order_mock.return_value = buy_order_result

        with open('./ccxt_order_result/limit/limit_buy_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        class TestStrategy(Strategy):

            def next(self):
                self.buy(size=2.0, exectype=Order.Limit, price=5.4326)
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='limit',
            side='buy',
            amount=2.0,
            price=5.4326,
            params={},
        )

    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_limit_sell(self, binance_create_order_mock, fetch_order_mock):
        with open('./ccxt_order_result/limit/limit_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/limit/limit_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        class TestStrategy(Strategy):

            def next(self):
                self.sell(size=2.0, exectype=Order.Limit, price=5.4326)
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='limit',
            side='sell',
            amount=2.0,
            price=5.4326,
            params={},
        )

    @patch('ccxt.binance.cancel_order')
    @patch('ccxt.binance.fetch_order')
    def test_cancel(self, cancel_fetch_order_mock, binance_cancel_order_mock):
        with open('./ccxt_order_result/limit/limit_buy_fetch_order.json', 'r') as f:
            ccxt_buy_order = json.load(f)

        with open('./ccxt_order_result/cancel_fetch_order.json', 'r') as f:
            cancel_fetch_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/cancel.json', 'r') as f:
            binance_cancel_order_mock.return_value = json.load(f)

        class TestStrategy(Strategy):

            def next(self):
                self.cancel(CCXTOrder(
                    None,
                    self.datas[0],
                    ccxt_buy_order
                ))
                self.env.runstop()

        trading.main(TestStrategy)

        binance_cancel_order_mock.assert_called_once_with(ANY, 'BNB/USDT')

    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_market_buy(self, binance_create_order_mock, fetch_order_mock):
        with open('./ccxt_order_result/market/market_buy.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_buy_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        class TestStrategy(Strategy):

            def next(self):
                self.buy(size=1.0)
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='market',
            side='buy',
            amount=1.0,
            price=None,
            params={},
        )

    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_market_sell(self, binance_create_order_mock, fetch_order_mock):
        with open('./ccxt_order_result/market/market_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        class TestStrategy(Strategy):

            def next(self):
                self.sell(size=1.0)
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='market',
            side='sell',
            amount=1.0,
            price=None,
            params={},
        )

    @patch('ccxt.binance.fetch_ohlcv')
    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_stop_loss_sell_below_market(self, binance_create_order_mock, fetch_order_mock, fetch_ohlcv_mock):
        with open('./ccxt_order_result/market/market_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        # open-time, open, high, low, close, volume
        fetch_ohlcv_mock.return_value = [[1552001400000, 15.112, 15.1184, 15.112, 15.1184, 98.9]]

        class TestStrategy(Strategy):

            def next(self):
                sell_order = self.sell(size=1.0, exectype=Order.StopLimit,
                                       price=10.9,  # stopPrice=10.9,
                                       plimit=9.9)  # price=9.9
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='STOP_LOSS_LIMIT',
            side='sell',
            amount=1.0,
            price=9.9,
            params={'stopPrice': 10.9},
        )

    @patch('ccxt.binance.fetch_ohlcv')
    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_stop_loss_sell_above_market(self, binance_create_order_mock, fetch_order_mock, fetch_ohlcv_mock):
        with open('./ccxt_order_result/market/market_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        # open-time, open, high, low, close, volume
        fetch_ohlcv_mock.return_value = [[1552001400000, 5.112, 5.1184, 5.112, 5.1184, 98.9]]

        class TestStrategy(Strategy):

            def next(self):
                sell_order = self.sell(size=1.0, exectype=Order.StopLimit,
                                       price=10.9,  # stopPrice=10.9,
                                       plimit=9.9)  # price=9.9
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='TAKE_PROFIT_LIMIT',
            side='sell',
            amount=1.0,
            price=9.9,
            params={'stopPrice': 10.9},
        )

    @patch('ccxt.binance.fetch_ohlcv')
    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_stop_loss_buy_below_market(self, binance_create_order_mock, fetch_order_mock, fetch_ohlcv_mock):
        with open('./ccxt_order_result/market/market_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        # open-time, open, high, low, close, volume
        fetch_ohlcv_mock.return_value = [[1552001400000, 15.112, 15.1184, 15.112, 15.1184, 98.9]]

        class TestStrategy(Strategy):

            def next(self):
                sell_order = self.buy(size=1.0, exectype=Order.StopLimit,
                                      price=10.9,  # stopPrice=10.9,
                                      plimit=11.9)  # price=9.9
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='TAKE_PROFIT_LIMIT',
            side='buy',
            amount=1.0,
            price=11.9,
            params={'stopPrice': 10.9},
        )

    @patch('ccxt.binance.fetch_ohlcv')
    @patch('ccxt.binance.fetch_order')
    @patch('ccxt.binance.create_order')
    def test_stop_loss_buy_above_market(self, binance_create_order_mock, fetch_order_mock, fetch_ohlcv_mock):
        with open('./ccxt_order_result/market/market_sell.json', 'r') as f:
            binance_create_order_mock.return_value = json.load(f)

        with open('./ccxt_order_result/market/market_sell_fetch_order.json', 'r') as f:
            fetch_order_mock.return_value = json.load(f)

        # open-time, open, high, low, close, volume
        fetch_ohlcv_mock.return_value = [[1552001400000, 5.112, 5.1184, 5.112, 5.1184, 98.9]]

        class TestStrategy(Strategy):

            def next(self):
                sell_order = self.buy(size=1.0, exectype=Order.StopLimit,
                                      price=10.9,  # stopPrice=10.9,
                                      plimit=11.9)  # price=9.9
                self.env.runstop()

        trading.main(TestStrategy)

        binance_create_order_mock.assert_called_once_with(
            symbol='BNB/USDT',
            type='STOP_LOSS_LIMIT',
            side='buy',
            amount=1.0,
            price=11.9,
            params={'stopPrice': 10.9},
        )


if __name__ == '__main__':
    unittest.main()
