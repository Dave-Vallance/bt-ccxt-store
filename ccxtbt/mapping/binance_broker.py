from backtrader import Order

from ccxtbt import CCXTBroker


class BinanceBroker(CCXTBroker):
    """
    Binance uses specific order types for stop limit orders that cannot easily be mapped
    with a static mapping file. The logic for that and for specific price parameters are
    implemented in this Binance broker.
    This way the strategies can be implemented with the execution types and parameters
    that are needed by Backtrader. They are converted to the format needed by Binance
    here.
    The strategy code for backtesting and for running it on Binance can stay the same.
    """

    mapping = {
        "order_types": {
            "Market": "market",
            "Limit": "limit",
            "Stop": "stop-loss",
        },
        "order_status": {
            "closed_order": {
                "key": "status",
                "value": "closed"
            },
            "canceled_order": {
                "key": "status",
                "value": "canceled"
            }
        }
    }

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            **kwargs):
        """
        Gets called from the strategy, modifies the parameter as needed and forwards them to the CCXTBroker.
        """
        del kwargs['parent']
        del kwargs['transmit']
        if exectype == Order.StopLimit:
            return self.stop_limit_buy(owner, data, size, price, plimit, kwargs)
        else:
            order_type = self.get_order_type(exectype, self.mapping)
            return self._submit(owner, data, order_type, 'buy', size, price, kwargs)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             **kwargs):
        """
        Gets called from the strategy, modifies the parameter as needed and forwards them to the CCXTBroker.
        """
        del kwargs['parent']
        del kwargs['transmit']

        if exectype == Order.StopLimit:
            return self.stop_limit_sell(owner, data, size, price, plimit, kwargs)
        else:
            order_type = self.get_order_type(exectype, self.mapping)
            return self._submit(owner, data, order_type, 'sell', size, price, kwargs)

    def stop_limit_sell(self, owner, data, size, price, plimit, kwargs):
        stop_price = price
        limit_price = plimit
        market_price = self.get_market_price(data.symbol)
        # see https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#new-order--trade
        order_type = 'STOP_LOSS_LIMIT' if stop_price < market_price else 'TAKE_PROFIT_LIMIT'
        return self._submit(owner, data, order_type, 'sell', size, limit_price,
                            dict(kwargs, stopPrice=stop_price))

    def stop_limit_buy(self, owner, data, size, price, plimit, kwargs):
        stop_price = price
        limit_price = plimit
        market_price = self.get_market_price(data.symbol)
        # see https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#new-order--trade
        order_type = 'TAKE_PROFIT_LIMIT' if stop_price < market_price else 'STOP_LOSS_LIMIT'
        return self._submit(owner, data, order_type, 'buy', size, limit_price, dict(kwargs, stopPrice=stop_price))

    def get_market_price(self, symbol):
        open_time, open, high, low, close, volume = self.store.fetch_ohlcv(
            symbol=symbol,
            timeframe='1m',
            since=None,
            limit=1)[0]
        return close

    def get_order_status_values(self, ccxt_order, status_type, broker_mapping):
        """
        Gets called from CCXTBroker and returns the Binance mapping.
        :param ccxt_order:
        :param status_type:
        :param broker_mapping:
        :return:
        """
        return super().get_order_status_values(ccxt_order, status_type, self.mapping)
