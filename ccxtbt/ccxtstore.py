#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2017 Ed Bartosh <bartosh@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json
import time
from datetime import datetime
from functools import wraps

import backtrader as bt
import ccxt
from backtrader.metabase import MetaParams
from backtrader.utils.py3 import with_metaclass
from ccxt.base.errors import NetworkError, ExchangeError

import ccxtbt
from definitions import MAPPING_PATH


class MetaSingleton(MetaParams):
    '''Metaclass to make a metaclassed class a singleton'''

    def __init__(cls, name, bases, dct):
        super(MetaSingleton, cls).__init__(name, bases, dct)
        cls._singleton = None

    def __call__(cls, *args, **kwargs):
        if cls._singleton is None:
            cls._singleton = (
                super(MetaSingleton, cls).__call__(*args, **kwargs))

        return cls._singleton


class CCXTStore(with_metaclass(MetaSingleton, object)):
    '''API provider for CCXT feed and broker classes.

    Added a new get_wallet_balance method. This will allow manual checking of the balance.
        The method will allow setting parameters. Useful for getting margin balances

    Added new private_end_point method to allow using any private non-unified end point

    '''

    # Supported granularities
    _GRANULARITIES = {
        (bt.TimeFrame.Minutes, 1): '1m',
        (bt.TimeFrame.Minutes, 3): '3m',
        (bt.TimeFrame.Minutes, 5): '5m',
        (bt.TimeFrame.Minutes, 15): '15m',
        (bt.TimeFrame.Minutes, 30): '30m',
        (bt.TimeFrame.Minutes, 60): '1h',
        (bt.TimeFrame.Minutes, 90): '90m',
        (bt.TimeFrame.Minutes, 120): '2h',
        (bt.TimeFrame.Minutes, 180): '3h',
        (bt.TimeFrame.Minutes, 240): '4h',
        (bt.TimeFrame.Minutes, 360): '6h',
        (bt.TimeFrame.Minutes, 480): '8h',
        (bt.TimeFrame.Minutes, 720): '12h',
        (bt.TimeFrame.Days, 1): '1d',
        (bt.TimeFrame.Days, 3): '3d',
        (bt.TimeFrame.Weeks, 1): '1w',
        (bt.TimeFrame.Weeks, 2): '2w',
        (bt.TimeFrame.Months, 1): '1M',
        (bt.TimeFrame.Months, 3): '3M',
        (bt.TimeFrame.Months, 6): '6M',
        (bt.TimeFrame.Years, 1): '1y',
    }

    BrokerCls = None  # broker class will auto register
    DataCls = None  # data class will auto register

    @classmethod
    def getdata(cls, *args, **kwargs):
        '''Returns ``DataCls`` with args, kwargs'''
        return cls.DataCls(*args, **kwargs)

    @classmethod
    def getbroker(cls, broker_mapping=None, *args, **kwargs):
        new_broker_mapping = cls.load_broker_mappings(broker_mapping, exchange=cls._singleton.exchange.name)
        if 'broker_class' in new_broker_mapping:
            return getattr(ccxtbt.mapping, "BinanceBroker")(broker_mapping=new_broker_mapping, *args, **kwargs)
        else:
            # Returns broker with *args, **kwargs from registered ``BrokerCls``
            return cls.BrokerCls(broker_mapping=new_broker_mapping, *args, **kwargs)

    @classmethod
    def load_broker_mappings(cls, broker_mapping2overwrite, exchange):
        """
        Expected format for broker_mapping2overwrite:
        broker_mapping = {
            'order_types': {
                bt.Order.Market: 'market',
                bt.Order.Limit: 'limit',
                bt.Order.Stop: 'stop-loss',
                bt.Order.StopLimit: 'stop limit'
            },
            'mappings': {
                'closed_order': {
                    'key': 'status',
                    'value': 'closed'
                },
                'canceled_order': {
                    'key': 'result',
                    'value': 1}
            }
        }
        """
        if broker_mapping2overwrite:
            broker_mapping = {
                "order_types": {
                    "Market": broker_mapping2overwrite['order_types'][bt.Order.Market],
                    "Limit": broker_mapping2overwrite['order_types'][bt.Order.Limit],
                    "Stop": broker_mapping2overwrite['order_types'][bt.Order.Stop],
                    "StopLimit": broker_mapping2overwrite['order_types'][bt.Order.StopLimit]
                },
                "order_status": {
                    "closed_order": {
                        "key": broker_mapping2overwrite['mappings']['closed_order']['key'],
                        "value": broker_mapping2overwrite['mappings']['closed_order']['value']
                    },
                    "canceled_order": {
                        "key": broker_mapping2overwrite['mappings']['canceled_order']['key'],
                        "value": broker_mapping2overwrite['mappings']['canceled_order']['value']
                    }
                }
            }
            return broker_mapping
        else:
            # load the general mappings file
            with open(MAPPING_PATH, 'r') as f:
                broker_mappings = json.load(f)
                try:
                    broker_mapping = broker_mappings["exchanges"][exchange]
                    # load only the default version for now
                    broker_mapping = broker_mapping["version"]["default"]
                except KeyError:
                    # use the default exchange mapping if there is non for the currently used exchange
                    broker_mapping = broker_mappings["exchanges"]["default"]
                return broker_mapping

    def __init__(self, exchange, currency, config, retries, broker_delay=None, debug=False):
        self.exchange = getattr(ccxt, exchange)(config)
        self.currency = currency
        self.retries = retries
        self.debug = debug

        balance = self.exchange.fetch_balance()
        self._cash = balance['free'][currency]
        self._value = balance['total'][currency]

    def get_granularity(self, timeframe, compression):
        if not self.exchange.has['fetchOHLCV']:
            raise NotImplementedError("'%s' exchange doesn't support fetching OHLCV data" % \
                                      self.exchange.name)

        granularity = self._GRANULARITIES.get((timeframe, compression))
        if granularity is None:
            raise ValueError("backtrader CCXT module doesn't support fetching OHLCV "
                             "data for time frame %s, comression %s" % \
                             (bt.TimeFrame.getname(timeframe), compression))

        if self.exchange.timeframes and granularity not in self.exchange.timeframes:
            raise ValueError("'%s' exchange doesn't support fetching OHLCV data for "
                             "%s time frame" % (self.exchange.name, granularity))

        return granularity

    def retry(method):
        @wraps(method)
        def retry_method(self, *args, **kwargs):
            for i in range(self.retries):
                if self.debug:
                    print('{} - {} - Attempt {}'.format(datetime.now(), method.__name__, i))
                time.sleep(self.exchange.rateLimit / 1000)
                try:
                    return method(self, *args, **kwargs)
                except (NetworkError, ExchangeError):
                    if i == self.retries - 1:
                        raise

        return retry_method

    @retry
    def get_wallet_balance(self, currency, params=None):
        balance = self.exchange.fetch_balance(params)
        return balance

    @retry
    def get_balance(self):
        balance = self.exchange.fetch_balance()
        self._cash = balance['free'][self.currency]
        self._value = balance['total'][self.currency]

    @retry
    def getposition(self):
        return self._value
        # return self.getvalue(currency)

    @retry
    def create_order(self, symbol, order_type, side, amount, price, params):
        # returns the order
        return self.exchange.create_order(symbol=symbol, type=order_type, side=side,
                                          amount=amount, price=price, params=params)

    @retry
    def cancel_order(self, order_id, symbol):
        return self.exchange.cancel_order(order_id, symbol)

    @retry
    def fetch_trades(self, symbol):
        return self.exchange.fetch_trades(symbol)

    @retry
    def fetch_ohlcv(self, symbol, timeframe, since, limit, params={}):
        if self.debug:
            print('Fetching: {}, TF: {}, Since: {}, Limit: {}'.format(symbol, timeframe, since, limit))
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params=params)

    @retry
    def fetch_order(self, oid, symbol):
        return self.exchange.fetch_order(oid, symbol)

    @retry
    def fetch_open_orders(self):
        return self.exchange.fetchOpenOrders()

    @retry
    def private_end_point(self, type, endpoint, params):
        '''
        Open method to allow calls to be made to any private end point.
        See here: https://github.com/ccxt/ccxt/wiki/Manual#implicit-api-methods

        - type: String, 'Get', 'Post','Put' or 'Delete'.
        - endpoint = String containing the endpoint address eg. 'order/{id}/cancel'
        - Params: Dict: An implicit method takes a dictionary of parameters, sends
          the request to the exchange and returns an exchange-specific JSON
          result from the API as is, unparsed.

        To get a list of all available methods with an exchange instance,
        including implicit methods and unified methods you can simply do the
        following:

        print(dir(ccxt.hitbtc()))
        '''
        return getattr(self.exchange, endpoint)(params)
