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

import copy
import inspect
import json
import time
import traceback
from datetime import datetime
from functools import wraps
from pprint import pprint

import backtrader
import backtrader as bt
import ccxt
from pybit import usdt_perpetual

from backtrader.metabase import MetaParams
from backtrader.utils.py3 import with_metaclass
from ccxt.base.errors import NetworkError, ExchangeError


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
    def getbroker(cls, *args, **kwargs):
        '''Returns broker with *args, **kwargs from registered ``BrokerCls``'''
        return cls.BrokerCls(*args, **kwargs)

    def __init__(self, exchange, currency, config, retries, debug=False, sandbox=False):
        self.exchange = getattr(ccxt, exchange)(config)
        self.mainnet_exchange = getattr(ccxt, exchange)(config)
        if sandbox:
            self.exchange.set_sandbox_mode(True)

        # INFO: Invoke websocket if available
        self.is_ws_available = False
        self.ws_usdt_perpetual = None
        if exchange == 'bybit':
            self.is_ws_available = True
            # Connect with authentication
            self.ws_usdt_perpetual = usdt_perpetual.WebSocket(
                test=sandbox,
                api_key=config['apiKey'],
                api_secret=config['secret'],
                # to pass a custom domain in case of connectivity problems, you can use:
                domain="bytick"  # the default is "bybit"
            )
            self.ws_usdt_perpetual.order_stream(self.handle_active_order)
            self.ws_usdt_perpetual.stop_order_stream(self.handle_conditional_order)
            self.ws_usdt_perpetual.position_stream(self.handle_positions)
        self.ws_positions = []
        self.ws_active_orders = []
        self.ws_conditional_orders = []

        self.currency = currency
        self.retries = retries
        self.debug = debug
        balance = self.exchange.fetch_balance() if 'secret' in config else 0
        try:
            if balance == 0 or not balance['free'][currency]:
                self._cash = 0
            else:
                self._cash = balance['free'][currency]
        except KeyError:  # never funded or eg. all USD exchanged 
            self._cash = 0
        try:
            if balance == 0 or not balance['total'][currency]:
                self._value = 0
            else:
                self._value = balance['total'][currency]
        except KeyError:
            self._value = 0

    def get_granularity(self, timeframe, compression):
        if not self.exchange.has['fetchOHLCV']:
            raise NotImplementedError("'%s' exchange doesn't support fetching OHLCV data" % \
                                      self.exchange.name)

        granularity = self._GRANULARITIES.get((timeframe, compression))
        if granularity is None:
            raise ValueError("backtrader CCXT module doesn't support fetching OHLCV "
                             "data for time frame %s, compression %s" % \
                             (bt.TimeFrame.getname(timeframe), compression))

        if self.exchange.timeframes and granularity not in self.exchange.timeframes:
            raise ValueError("'%s' exchange doesn't support fetching OHLCV data for "
                             "%s time frame" % (self.exchange.name, granularity))

        return granularity

    def handle_positions(self, message):
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            assert type(message['data']) == list
            responses = self.exchange.safe_value(message, 'data')
            for i, position in enumerate(responses):
                # print("{} Line: {}: position:".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                # ))
                # pprint(position)
                if position not in self.ws_positions:
                    self.ws_positions.append(position)
                self.ws_positions[i] = position

            # Sort dictionary list by key
            reverse = False
            sort_by_key = 'side'
            self.ws_positions = sorted(self.ws_positions,
                                       key=lambda k: k[sort_by_key],
                                       reverse=reverse)
        except Exception:
            traceback.print_exc()

    def handle_active_order(self, message):
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            responses = message['data']
            assert type(responses) == list
            active_orders_to_be_added = []
            for order in responses:
                market = self.exchange.market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                active_order = self.exchange.parse_order(result[0], market)

                # INFO: Strip away "/" and ":USDT"
                active_order['symbol'] = active_order['symbol'].replace("/", "")
                active_order['symbol'] = active_order['symbol'].replace(":USDT", "")

                # print("{} Line: {}: DEBUG: active_order:".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                # ))
                # pprint(active_order)

                # print("{} Line: {}: DEBUG: Added active_order ID: {}".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                #     active_order['id'],
                # ))
                active_orders_to_be_added.append(active_order)

            active_order_ids_to_be_added = [active_order['id'] for active_order in active_orders_to_be_added]

            # INFO: Look for existing order in the list
            ws_active_orders_to_be_removed = []
            for ws_active_order in self.ws_active_orders:
                if ws_active_order['id'] in active_order_ids_to_be_added:
                    ws_active_orders_to_be_removed.append(ws_active_order)

            # INFO: Remove the existing ws active order
            for ws_active_order in ws_active_orders_to_be_removed:
                self.ws_active_orders.remove(ws_active_order)

            # INFO: Add the latest active orders
            for active_order in active_orders_to_be_added:
                self.ws_active_orders.append(active_order)
        except Exception:
            traceback.print_exc()

    def handle_conditional_order(self, message):
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            responses = message['data']
            assert type(responses) == list
            for order in responses:
                market = self.exchange.market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                conditional_order = self.exchange.parse_order(result[0], market)

                # INFO: Strip away "/" and ":USDT"
                conditional_order['symbol'] = conditional_order['symbol'].replace("/", "")
                conditional_order['symbol'] = conditional_order['symbol'].replace(":USDT", "")

                # print("{} Line: {}: DEBUG: conditional_order:".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                # ))
                # pprint(conditional_order)

                # print("{} Line: {}: DEBUG: Added conditional_order ID: {}".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                #     conditional_order['id'],
                # ))
                self.ws_conditional_orders.append(conditional_order)
        except Exception:
            traceback.print_exc()

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

        cash = balance['free'][self.currency]
        value = balance['total'][self.currency]
        # Fix if None is returned
        self._cash = cash if cash else 0
        self._value = value if value else 0

    def get_position(self):
        return self._value

    @retry
    def create_order(self, symbol, order_type, side, amount, price, params):
        # returns the order
        return self.exchange.create_order(symbol=symbol, type=order_type, side=side,
                                          amount=amount, price=price, params=params)

    @retry
    def edit_order(self, order_id, symbol, *arg):
        # returns the order
        return self.exchange.edit_order(order_id, symbol, *arg)

    @retry
    def cancel_order(self, order_id, symbol):
        return self.exchange.cancel_order(order_id, symbol)

    @retry
    def fetch_trades(self, symbol):
        return self.exchange.fetch_trades(symbol)

    @retry
    def parse_timeframe(self, timeframe):
        return self.exchange.parse_timeframe(timeframe)

    @retry
    def filter_by_since_limit(self, array, since=None, limit=None, key='timestamp', tail=False):
        return self.exchange.filter_by_since_limit(array, since, limit, key, tail)

    @retry
    def fetch_ohlcv(self, symbol, timeframe, since, limit, params={}):
        if self.debug:
            since_dt = datetime.utcfromtimestamp(since // 1000) if since is not None else 'NA'
            print('Fetching: {}, timeframe:{}, since TS:{}, since_dt:{}, limit:{}, params:{}'.format(
                symbol, timeframe, since, since_dt, limit, params))
        # INFO: Always fetch klines from mainnet instead of testnet
        return self.mainnet_exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params=params)

    @retry
    def fetch_order_book(self, symbol, limit=None, params={}):
        # INFO: Always fetch order book from mainnet instead of testnet
        return self.mainnet_exchange.fetch_order_book(symbol, limit=limit, params=params)

    @retry
    def _fetch_order_from_exchange(self, oid, symbol, params={}):
        order = self.exchange.fetch_order(oid, symbol, params)
        return order

    def fetch_order(self, oid, symbol, params={}):
        # print("{} Line: {}: is_ws_available: {}".format(
        #     inspect.getframeinfo(inspect.currentframe()).function,
        #     inspect.getframeinfo(inspect.currentframe()).lineno,
        #     self.is_ws_available,
        # ))

        if self.is_ws_available == True:
            found_ws_order = False
            # If we are looking for Active Order
            if oid is not None:
                # print("{} Line: {}: Searching for active_order ID: {}".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                #     oid,
                # ))

                for active_order in self.ws_active_orders:
                    # print("{} Line: {}: Comparing active_order ID: {}".format(
                    #     inspect.getframeinfo(inspect.currentframe()).function,
                    #     inspect.getframeinfo(inspect.currentframe()).lineno,
                    #     active_order['id'],
                    # ))

                    if oid == active_order['id']:
                        # Extract the order from the websocket
                        order = active_order
                        # self.ws_active_orders.remove(active_order)
                        found_ws_order = True
                        break
            # Else if we are looking for Conditional Order
            else:
                conditional_oid = params['stop_order_id']
                for conditional_order in self.ws_conditional_orders:
                    if conditional_oid == conditional_order['id']:
                        # Extract the order from the websocket
                        order = conditional_order
                        # self.ws_conditional_orders.remove(conditional_order)
                        found_ws_order = True
                        break

            # print("")
            # if oid is not None:
            #     print("{} Line: {}: INFO: found_ws_order: {} for active_order: {}".format(
            #         inspect.getframeinfo(inspect.currentframe()).function,
            #         inspect.getframeinfo(inspect.currentframe()).lineno,
            #         found_ws_order, oid,
            #     ))
            # else:
            #     conditional_oid = params['stop_order_id']
            #     print("{} Line: {}: INFO: found_ws_order: {} for conditional_order: {}".format(
            #         inspect.getframeinfo(inspect.currentframe()).function,
            #         inspect.getframeinfo(inspect.currentframe()).lineno,
            #         found_ws_order, conditional_oid,
            #     ))

            if found_ws_order == False:
                # Exercise the longer time route
                order = self._fetch_order_from_exchange(oid, symbol, params)
        else:
            order = self._fetch_order_from_exchange(oid, symbol, params)
        return order

    @retry
    def fetch_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_orders(since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_orders(symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def fetch_opened_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_open_orders(since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_open_orders(symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def fetch_closed_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_closed_orders(since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_closed_orders(symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def _fetch_opened_positions_from_exchange(self, symbols=None, params={}):
        return self.exchange.fetch_positions(symbols=symbols, params=params)

    def fetch_opened_positions(self, symbols=None, params={}):
        if self.is_ws_available == True:
            if len(self.ws_positions) > 0:
                ret_positions = self.ws_positions
            else:
                # Exercise the longer time route
                ret_positions = self._fetch_opened_positions_from_exchange(symbols, params)
        else:
            ret_positions = self._fetch_opened_positions_from_exchange(symbols, params)
        return ret_positions

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
