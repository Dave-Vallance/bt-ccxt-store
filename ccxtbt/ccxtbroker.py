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
import json

from backtrader import BrokerBase, OrderBase
from backtrader.position import Position
from backtrader.utils.py3 import queue, with_metaclass

from .ccxtstore import CCXTStore


class CCXTOrder(OrderBase):
    def __init__(self, owner, data, ccxt_order):
        self.owner = owner
        self.data = data
        self.ccxt_order = ccxt_order
        self.ordtype = self.Buy if ccxt_order['side'] == 'buy' else self.Sell
        self.size = float(ccxt_order['amount'])

        super(CCXTOrder, self).__init__()


class MetaCCXTBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaCCXTBroker, cls).__init__(name, bases, dct)
        if name == 'CCXTBroker':
            CCXTStore.BrokerCls = cls


class CCXTBroker(with_metaclass(MetaCCXTBroker, BrokerBase)):
    '''Broker implementation for CCXT cryptocurrency trading library.
    This class maps the orders/positions from CCXT to the
    internal API of ``backtrader``.

    Broker mapping added as I noticed that there differences between the expected
    order_types and retuned status's from canceling an order

    Added a new mapping parameter to the script with defaults.

    Added a get_balance function. Manually check the account balance and update brokers
    self.cash and self.value. This helps alleviate rate limit issues.

    Added a new get_wallet_balance method. This will allow manual checking of the any coins
        The method will allow setting parameters. Useful for dealing with multiple assets

    Modified getcash() and getvalue():
        Backtrader will call getcash and getvalue before and after next, slowing things down
        with rest calls. As such, th

    The broker mapping should contain a new dict for order_types and order_status like below:

    broker_mapping = {
        'order_types': {
            bt.Order.Market: 'market',
            bt.Order.Limit: 'limit',
            bt.Order.Stop: 'stop-loss', #stop-loss for kraken, stop for bitmex
            bt.Order.StopLimit: 'stop limit'
        },
        'order_status':{
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

    broker_mapping = None

    def __init__(self, broker_mapping=None, debug=False, **kwargs):
        super(CCXTBroker, self).__init__()

        self.store = CCXTStore(**kwargs)

        self.broker_mapping = broker_mapping

        self.currency = self.store.currency

        self.positions = collections.defaultdict(Position)

        self.debug = debug
        self.indent = 4  # For pretty printing dictionaries

        self.notifs = queue.Queue()  # holds orders which are notified

        self.open_orders = list()

        self.startingcash = self.store._cash
        self.startingvalue = self.store._value

    def get_balance(self):
        balance = self.store.get_balance()
        self.cash = self.store._cash
        self.value = self.store._value
        return self.cash, self.value

    def get_wallet_balance(self, currency, params={}):
        balance = self.store.get_wallet_balance(currency, params=params)
        cash = balance['free'][currency]
        value = balance['total'][currency]
        return cash, value

    def getcash(self):
        # Get cash seems to always be called before get value
        # Therefore it makes sense to add getbalance here.
        # return self.store.getcash(self.currency)
        self.cash = self.store._cash
        return self.cash

    def getvalue(self, datas=None):
        # return self.store.getvalue(self.currency)
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
        # return self.o.getposition(data._dataname, clone=clone)
        pos = self.positions[data._dataname]
        if clone:
            pos = pos.clone()
        return pos

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
            ccxt_order = self.store.fetch_order(oID, o_order.data.symbol)

            if self.debug:
                print(json.dumps(ccxt_order, indent=self.indent))

            # Check if the order is closed
            closed_order_exchange_value, closed_order_success_value = self.get_order_status_values(ccxt_order,
                                                                                                   'closed_order',
                                                                                                   self.broker_mapping)
            if closed_order_exchange_value == closed_order_success_value:
                pos = self.getposition(o_order.data, clone=False)
                pos.update(o_order.size, o_order.price)
                o_order.completed()
                self.notify(o_order)
                self.open_orders.remove(o_order)

    def _submit(self, owner, data, exectype, side, amount, price, params):
        # order_type = self._get_order_type(exectype)
        if 'broker_class' in self.broker_mapping:
            order_type = exectype
        else:
            order_type = self.get_order_type(exectype, self.broker_mapping)

        # Extract CCXT specific params if passed to the order
        params = params['params'] if 'params' in params else params

        ret_ord = self.store.create_order(symbol=data.symbol, order_type=order_type, side=side,
                                          amount=amount, price=price, params=params)

        _order = self.store.fetch_order(ret_ord['id'], data.symbol)

        order = CCXTOrder(owner, data, _order)
        self.open_orders.append(order)

        self.notify(order)
        return order

    def get_order_type(self, exectype, broker_mapping):
        local_exec_type = exectype if exectype else OrderBase.Market
        order_type_name = OrderBase.ExecTypes[local_exec_type]
        order_types = broker_mapping['order_types']
        order_type = order_types.get(order_type_name)
        return order_type

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'buy', size, price, kwargs)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'sell', size, price, kwargs)

    def cancel(self, order):

        oID = order.ccxt_order['id']

        if self.debug:
            print('Broker cancel() called')
            print('Fetching Order ID: {}'.format(oID))

        # check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        ccxt_order = self.store.fetch_order(oID, order.data.symbol)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))

        closed_order_exchange_value, closed_order_success_value = self.get_order_status_values(ccxt_order,
                                                                                               'closed_order',
                                                                                               self.broker_mapping)
        if closed_order_exchange_value == closed_order_success_value:
            return order

        if self.debug:
            print('Canceling Order ID: {}'.format(oID))

        ccxt_order = self.store.cancel_order(oID, order.data.symbol)

        canceled_order_exchange_value, canceled_order_success_value = self.get_order_status_values(ccxt_order,
                                                                                                   'canceled_order',
                                                                                                   self.broker_mapping)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))
            print('Value Received: {}'.format(canceled_order_exchange_value))
            print('Value Expected: {}'.format(canceled_order_success_value))

        if canceled_order_exchange_value == canceled_order_success_value:
            if order in self.open_orders:
                self.open_orders.remove(order)
            order.cancel()
            self.notify(order)
        return order

    def get_order_status_values(self, ccxt_order, status_type, broker_mapping):
        exchange_status_key = broker_mapping['order_status'][status_type]['key']
        success_order_status_value = broker_mapping['order_status'][status_type]['value']
        exchange_status_value = ccxt_order[exchange_status_key]
        return exchange_status_value, success_order_status_value

    def get_orders_open(self, safe=False):
        return self.store.fetch_open_orders()

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
        endpoint_str = endpoint.replace('/', '_')
        endpoint_str = endpoint_str.replace('{', '')
        endpoint_str = endpoint_str.replace('}', '')

        method_str = 'private_' + type.lower() + endpoint_str.lower()

        return self.store.private_end_point(type=type, endpoint=method_str, params=params)
