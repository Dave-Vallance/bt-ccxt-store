#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016, 2017 Daniel Rodriguez
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

import collections
import inspect
import json
import datetime

from backtrader import BrokerBase, OrderBase, Order
from backtrader.position import Position
from backtrader.utils.py3 import queue, with_metaclass
from time import time as timer

from .ccxtstore import CCXTStore
from .utils import print_timestamp_checkpoint


class CCXTOrder(OrderBase):
    def __init__(self, owner, data, ccxt_order):
        self.owner = owner
        self.data = data
        self.ccxt_order = ccxt_order
        self.executed_fills = []
        self.ordtype = self.Buy if ccxt_order['side'] == 'buy' else self.Sell
        self.size = float(ccxt_order['amount'])

        super(CCXTOrder, self).__init__()


class MetaCCXTBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaCCXTBroker, cls).__init__(name, bases, dct)
        CCXTStore.BrokerCls = cls


class CCXTBroker(with_metaclass(MetaCCXTBroker, BrokerBase)):
    '''Broker implementation for CCXT cryptocurrency trading library.
    This class maps the orders/positions from CCXT to the
    internal API of ``backtrader``.

    Broker mapping added as I noticed that there differences between the expected
    order_types and retuned status's from canceling an order

    Added a new mappings parameter to the script with defaults.

    Added a get_balance function. Manually check the account balance and update brokers
    self.cash and self.value. This helps alleviate rate limit issues.

    Added a new get_wallet_balance method. This will allow manual checking of the any coins
        The method will allow setting parameters. Useful for dealing with multiple assets

    Modified getcash() and getvalue():
        Backtrader will call getcash and getvalue before and after next, slowing things down
        with rest calls. As such, th

    The broker mapping should contain a new dict for order_types and mappings like below:

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

    Added new private_end_point method to allow using any private non-unified end point

    '''

    order_types = {Order.Market: 'market',
                   Order.Limit: 'limit',
                   Order.Stop: 'stop',  # stop-loss for kraken, stop for bitmex
                   Order.StopLimit: 'stop limit'}

    mappings = {
        'closed_order': {
            'key': 'status',
            'value': 'closed'
        },
        'canceled_order': {
            'key': 'status',
            'value': 'canceled'}
    }

    def __init__(self, broker_mapping=None, debug=False, **kwargs):
        super(CCXTBroker, self).__init__()

        if broker_mapping is not None:
            try:
                self.order_types = broker_mapping['order_types']
            except KeyError:  # Might not want to change the order types
                pass
            try:
                self.mappings = broker_mapping['mappings']
            except KeyError:  # might not want to change the mappings
                pass

        self.store = CCXTStore(**kwargs)

        self.currency = self.store.currency

        self.positions = collections.defaultdict(Position)

        self.debug = debug
        self.indent = 4  # For pretty printing dictionaries

        self.notifs = queue.Queue()  # holds orders which are notified

        self.open_orders = list()

        self.startingcash = self.store._cash
        self.startingvalue = self.store._value

        self.use_order_params = True

    def get_balance(self):
        self.store.get_balance()
        self.cash = self.store._cash
        self.value = self.store._value
        return self.cash, self.value

    def get_wallet_balance(self, currency, params={}):
        balance = self.store.get_wallet_balance(currency, params=params)
        try:
            cash = balance['free'][currency] if balance['free'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            cash = 0
        try:
            value = balance['total'][currency] if balance['total'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            value = 0
        return cash, value

    def getcash(self, force=False):
        if force == True:
            self.store.get_balance()
        self.cash = self.store._cash
        return self.cash

    def getvalue(self, datas=None):
        self.value = self.store._value
        return self.value

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            return None

    def notify(self, order):
        self.notifs.put(order)

    def getposition(self, data, clone=True):
        ret_value = Position(size=0.0, price=0.0)
        for pos_data, pos in self.positions.items():
            if data._name == pos_data:
                if clone:
                    ret_value = pos.clone()
                else:
                    ret_value = pos
                break
        return ret_value

    def get_pnl(self, datas=None):
        pnl_comm = 0.0
        initial_margin_delta = 0.0

        for data in datas or self.positions:
            comminfo = self.getcommissioninfo(data)
            position = self.positions[data]

            if comminfo is not None:
                if position.size != 0.0:
                    per_data_pnl = comminfo.profitandloss(position.size, position.price, data.close[0])
                    entry_comm = comminfo.getcommission(position.size, position.price)
                    exit_comm = comminfo.getcommission(position.size, data.close[0])
                    pnl_comm += per_data_pnl - entry_comm - exit_comm
                    min_price = min(position.price, data.close[0])
                    max_price = max(position.price, data.close[0])
                    min_initial_margin = comminfo.get_initial_margin(position.size, min_price)
                    max_initial_margin = comminfo.get_initial_margin(position.size, max_price)
                    # INFO: This variable is created to normalized initial margin for both long and short position
                    #       so that pnl_in_percentage is somewhat similar between long and short position
                    initial_margin_delta += max_initial_margin - min_initial_margin

        pnl_in_percentage = pnl_comm / (initial_margin_delta or 1.0)
        return pnl_comm, pnl_in_percentage

    def next(self):
        if self.debug:
            print('Broker next() called')

        for o_order in list(self.open_orders):
            oID = o_order.ccxt_order['id']

            # Print debug before fetching so we know which order is giving an
            # issue if it crashes
            if self.debug:
                print('Fetching Order ID: {}'.format(oID))

            # Get the order
            ccxt_order = self.store.fetch_order(oID, o_order.data.p.dataname)

            # Check for new fills
            if 'trades' in ccxt_order and ccxt_order['trades'] is not None:
                for fill in ccxt_order['trades']:
                    if fill not in o_order.executed_fills:
                        o_order.execute(fill['datetime'], fill['amount'], fill['price'],
                                        0, 0.0, 0.0,
                                        0, 0.0, 0.0,
                                        0.0, 0.0,
                                        0, 0.0)
                        o_order.executed_fills.append(fill['id'])

            if self.debug:
                print(json.dumps(ccxt_order, indent=self.indent))

            # Check if the order is closed
            if ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
                pos = self.getposition(o_order.data, clone=False)
                pos.update(o_order.size, o_order.price)
                o_order.completed()
                self.notify(o_order)
                self.open_orders.remove(o_order)
                self.get_balance()

            # Manage case when an order is being Canceled from the Exchange
            #  from https://github.com/juancols/bt-ccxt-store/
            if ccxt_order[self.mappings['canceled_order']['key']] == self.mappings['canceled_order']['value']:
                self.open_orders.remove(o_order)
                o_order.cancel()
                self.notify(o_order)

    def _submit(self, owner, data, exectype, side, amount, price, simulated, params):
        if amount == 0 or price == 0:
        # do not allow failing orders
            return None
        order_type = self.order_types.get(exectype) if exectype else 'market'

        if data:
            created = int(data.datetime.datetime(0).timestamp()*1000)
            symbol_id = params['params']['symbol']
        else:
            # INFO: Use the current UTC datetime
            utc_dt = datetime.datetime.utcnow()
            created = int(utc_dt.timestamp()*1000)
            symbol_id = params['params']['symbol']
            # INFO: Remove symbol name from params
            params['params'].pop('symbol', None)

        # Extract CCXT specific params if passed to the order
        params = params['params'] if 'params' in params else params
        if not self.use_order_params:
            ret_ord = self.store.create_order(symbol=symbol_id, order_type=order_type, side=side,
                                              amount=amount, price=price, params={})
        else:
            try:
                # all params are exchange specific: https://github.com/ccxt/ccxt/wiki/Manual#custom-order-params
                params['created'] = created  # Add timestamp of order creation for backtesting
                ret_ord = self.store.create_order(symbol=symbol_id, order_type=order_type, side=side,
                                                  amount=amount, price=price, params=params)
            except:
                # save some API calls after failure
                self.use_order_params = False
                return None

        _order = self.store.fetch_order(ret_ord['id'], symbol_id)

        # INFO: Exposed simulated so that we could proceed with order without running cerebro
        order = CCXTOrder(owner, data, _order, simulated=simulated)

        # INFO: Retrieve order.price from _order['price'] is proven more reliable than ret_ord['price']
        order.price = _order['price']
        self.open_orders.append(order)

        self.notify(order)
        return order

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            simulated=False,
            **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'buy', size, price, simulated, kwargs)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             simulated=False,
             **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'sell', size, price, simulated, kwargs)

    def cancel(self, order):

        oID = order.ccxt_order['id']

        if self.debug:
            print('Broker cancel() called')
            print('Fetching Order ID: {}'.format(oID))

        # check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        ccxt_order = self.store.fetch_order(oID, order.data.p.dataname)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))

        if ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
            return order

        ccxt_order = self.store.cancel_order(oID, order.data.p.dataname)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))
            print('Value Received: {}'.format(ccxt_order[self.mappings['canceled_order']['key']]))
            print('Value Expected: {}'.format(self.mappings['canceled_order']['value']))

        if ccxt_order[self.mappings['canceled_order']['key']] == self.mappings['canceled_order']['value']:
            self.open_orders.remove(order)
            order.cancel()
            self.notify(order)
        return order

    def modify_order(self, order_id, symbol, *args):
        return self.store.edit_order(order_id, symbol, *args)

    def fetch_order(self, order_id, symbol, params={}):
        return self.store.fetch_order(order_id, symbol, params)

    def fetch_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_opened_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_opened_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_closed_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_closed_orders(symbol=symbol, since=since, limit=limit, params=params)

    def get_positions(self, symbols=None, params={}):
        return self.store.fetch_opened_positions(symbols, params)

    def __common_end_point(self, is_private, type, endpoint, params, prefix):
        endpoint_str = endpoint.replace('/', '_')
        endpoint_str = endpoint_str.replace('-', '_')
        endpoint_str = endpoint_str.replace('{', '')
        endpoint_str = endpoint_str.replace('}', '')

        private_or_public = "public"
        if is_private == True:
            private_or_public = "private"

        if prefix != "":
            method_str = prefix.lower() + "_" + private_or_public + "_" + type.lower() + endpoint_str.lower()
        else:
            method_str = private_or_public + "_" + type.lower() + endpoint_str.lower()

        return self.store.private_end_point(type=type, endpoint=method_str, params=params)

    def public_end_point(self, type, endpoint, params, prefix = ""):
        is_private = False
        return self.__common_end_point(is_private, type, endpoint, params, prefix)

    def private_end_point(self, type, endpoint, params, prefix = ""):
        '''
        Open method to allow calls to be made to any private end point.
        See here: https://github.com/ccxt/ccxt/wiki/Manual#implicit-api-methods

        - type: String, 'Get', 'Post','Put' or 'Delete'.
        - endpoint = String containing the endpoint address eg. 'order/{id}/cancel'
        - Params: Dict: An implicit method takes a dictionary of parameters, sends
          the request to the exchange and returns an exchange-specific JSON
          result from the API as is, unparsed.
        - Optional prefix to be appended to the front of method_str should your
          exchange needs it. E.g. v2_private_xxx

        To get a list of all available methods with an exchange instance,
        including implicit methods and unified methods you can simply do the
        following:

        print(dir(ccxt.hitbtc()))
        '''
        is_private = True
        return self.__common_end_point(is_private, type, endpoint, params, prefix)