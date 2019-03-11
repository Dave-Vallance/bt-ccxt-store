# bt-ccxt-store
A fork of Ed Bartosh's CCXT Store Work with some additions added for a projects
I have been working on.

Some additions have been made to this repo that I find useful. Your mileage may
vary.

Check out the sample scripts in `./samples` to see how to setup and run on Kraken and Binance.


# Additions / Changes

## CCXTBroker

- Added check for broker fills (complete notification, Cancel notification).
  Note that some exchanges may send different notification data

- Added a new get_wallet_balance method. This will allow manual checking of the balance.
  The method will allow setting parameters. Useful for getting margin balances

- Modified getcash() and getvalue():
      Backtrader will call getcash and getvalue before and after next, slowing things down
      with rest calls. As such, these will just return the last values called from getbalance().
      Because getbalance() will not be called by cerebro, you need to do this manually as and when  
      you want the information.
- Broker mapping:
     Naturally Backtrader uses general order types and doesn't know about specifics of 
     individual crypto exchanges. E.g. status names, order type names, parameter names,....
     This is why a mapping is needed between the parameter Backtrader passes on 
     and the ones CCXT sends to the crypto exchanges.

    Currently we support three means of mappings:
      
    1. The static internal mappings of order types and status.
        It can be found in `ccxtbt/resources/broker_mappings.json` and can be refined and
        extended on demand.
      
    2. The overwritable static mapping via `store.getbroker(broker_mapping=broker_mapping)` 
        see `test/ccxtbt/mapping/test_mapping_file_handling.py:test_overwritten_mapping()` 
      
    3. The overwritable broker methods to extend the mapping dynamically at runtime with custom logic. 
        This has been needed for Binance e.g. because it doesn't have a 1:1 mapping from the
        `stop-limit` Backtrader execution type to a single Binance order type constant. 
        The Binance constants depend on the stop price being above or below the market price 
        and on being a stop-limit buy order or a stop-limit sell order. 
        See `test/ccxtbt/mapping/test_binance_broker.py`.


  - Added new private_end_point method to allow using any private non-unified end point.
    An example for getting a list of postions and then closing them on Bitfinex
    is below:

```
      # NOTE - THIS CLOSES A LONG POSITION. TO CLOSE A SHORT, REMOVE THE '-' FROM
      # -self.position.size
      type = 'Post'
      endpoint = '/positions'
      params = {}
      positions = self.broker.private_end_point(type=type, endpoint=endpoint, params=params)
      for position in positions:
          id = position['id']
          type = 'Post'
          endpoint = '/position/close'
          params = {'position_id': id}
          result = self.broker.private_end_point(type=type, endpoint=endpoint, params=params)
          _pos = self.broker.getposition(data, clone=False)
          # A Price of NONE is returned form the close position endpoint!
          _pos.update(-self.position.size, None)

```

## CCXTStore

Redesigned the way that the store is intialized, data and brokers are requested.
The store now uses metaparams and has methods for `getbroker()` and `getdata()`.
A store is initialized in a similar way to other backtrader stores. e.g

```
# Create a cerebro
  cerebro = bt.Cerebro()

  config = {'urls': {'api': 'https://testnet.bitmex.com'},
                   'apiKey': apikey,
                   'secret': secret,
                   'enableRateLimit': enableRateLimit,
                  }

  # Create data feeds
  store = CCXTStore(exchange='bitmex', currency=currency, config=config, retries=5, debug=False)

  broker = store.getbroker()
  cerebro.setbroker(broker)

  hist_start_date = datetime.utcnow() - timedelta(minutes=fromMinutes)
  data = store.getdata(dataname=symbol, name="LTF",
                           timeframe=get_timeframe(timeframe), fromdate=hist_start_date,
                           compression=1, ohlcv_limit=50, fetch_ohlcv_params = {'partial': False}) #, historical=True)
```

 - Added new private_end_point method to allow using any private non-unified end point. For an example, see broker section above.

## CCXTFeed

- Added option to send some additional fetch_ohlcv_params. Some exchanges (e.g Bitmex) support sending some additional fetch parameters.
- Added drop_newest option to avoid loading incomplete candles where exchanges
  do not support sending ohlcv params to prevent returning partial data
- Added Debug option to enable some additional prints
