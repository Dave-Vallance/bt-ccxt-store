# bt-ccxt-store
A fork of Ed Bartosh's CCXT Store Work with some additions added for a projects
I have been working on.

Some additions have been made to this repo that I find useful. Your mileage may
vary.

Check out the example script to see how to setup and run on Kraken.


# Additions / Changes

## CCXTBroker

- Added check for broker fills (complete notification, Cancel notification).
  Note that some exchanges may send different notification data

- Broker mapping added as I noticed that there differences between the expected
  order_types and retuned status's from canceling an order

- Added a new mappings parameter to the script with defaults.

- Added a new get_wallet_balance method. This will allow manual checking of the balance.
  The method will allow setting parameters. Useful for getting margin balances

- Modified getcash() and getvalue():
      Backtrader will call getcash and getvalue before and after next, slowing things down
      with rest calls. As such, th

- **Note:** The broker mapping should contain a new dict for order_types and mappings like below:

```
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

## CCXTFeed

- Added option to send some additional fetch_ohlcv_params. Some exchanges (e.g Bitmex) support sending some additional fetch parameters.
- Added drop_newest option to avoid loading incomplete candles where exchanges
  do not support sending ohlcv params to prevent returning partial data
- Added Debug option to enable some additional prints
