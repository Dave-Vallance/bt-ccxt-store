import json
import os
import unittest
from unittest.mock import patch

from ccxtbt import CCXTStore, bt
from definitions import ROOT_PATH


class TestMappingFileHandling(unittest.TestCase):
    """
    Test the overwriting mechanism of the mapping file.
    """

    def setUp(self):
        self.test_mapping_folder_path_prefix = os.path.join(ROOT_PATH, 'test/ccxtbt/mapping/')
        self.mock_balance_path = self.test_mapping_folder_path_prefix + 'mock_balance.json'
        # Reset the singleton on every test run to avoid side effects between tests.
        CCXTStore.DataCls._store._singleton = None

    @patch('ccxt.acx.fetch_balance')
    def test_default_internal_mapping(self, fetch_balance_patcher):
        with open(self.mock_balance_path, 'r') as f:
            fetch_balance_patcher.return_value = json.load(f)

        store = CCXTStore(
            exchange='acx',
            currency='BTC',
            config={},
            retries=5)

        broker = store.getbroker()

        assert broker is not None, 'No default broker found'

        mapping = broker.broker_mapping
        assert mapping is not None, 'No mapping found'

        assert 'order_types' in mapping, 'No order types found'
        assert 'StopLimit' in mapping['order_types'], 'No \"StopLimit\" found in order types '
        assert mapping['order_types']['StopLimit'] == 'stop limit'

        assert 'order_status' in mapping, 'No order status found'
        assert 'closed_order' in mapping['order_status'], 'No \"closed_order\" found in order status'

        print(mapping)

    @patch('ccxt.kraken.fetch_balance')
    def test_specific_exchange_internal_mapping(self, fetch_balance_patcher):
        with open(self.mock_balance_path, 'r') as f:
            fetch_balance_patcher.return_value = json.load(f)

        store = CCXTStore(
            exchange='kraken',
            currency='BTC',
            config={},
            retries=5)

        broker = store.getbroker()
        assert broker is not None, 'No default broker found'

        mapping = broker.broker_mapping
        assert mapping is not None, 'No mapping found'

        assert 'order_types' in mapping, 'No order types found'
        assert 'StopLimit' in mapping['order_types'], 'No \"StopLimit\" found in order types '
        assert mapping['order_types']['StopLimit'] == 'stop limit', \
            'Expected the stop limit order type \"stop limit\" for Kraken'

        assert 'order_status' in mapping, 'No order status found'
        assert 'closed_order' in mapping['order_status'], 'No \"closed_order\" found in order status'

        print(mapping)

    @patch('ccxt.binance.fetch_balance')
    def test_overwritten_mapping(self, fetch_balance_patcher):
        with open(self.mock_balance_path, 'r') as f:
            fetch_balance_patcher.return_value = json.load(f)

        store = CCXTStore(
            exchange='binance',
            currency='BNB',
            config={},
            retries=5)

        broker_mapping = {
            'order_types': {
                bt.Order.Market: 'market',
                bt.Order.Limit: 'limit',
                bt.Order.Stop: 'stop-loss',
                bt.Order.StopLimit: 'a specific stop limit type'
            },
            'mappings': {
                'closed_order': {
                    'key': 'status',
                    'value': 'closed'
                },
                'canceled_order': {
                    'key': 'status',
                    'value': 'canceled'}
            }
        }

        broker = store.getbroker(broker_mapping=broker_mapping)

        assert broker is not None, 'No default broker found'

        mapping = broker.broker_mapping
        assert mapping is not None, 'No mapping found'

        assert 'order_types' in mapping, 'No order types found'
        assert 'StopLimit' in mapping['order_types'], 'No \"StopLimit\" found in order types '
        assert mapping['order_types']['StopLimit'] == 'a specific stop limit type', \
            'Expected the stop limit order type \"STOP_LOSS_LIMIT\" for this overwritten mapping'

        assert 'order_status' in mapping, 'No order status found'
        assert 'closed_order' in mapping['order_status'], 'No \"closed_order\" found in order status'


if __name__ == '__main__':
    unittest.main()
