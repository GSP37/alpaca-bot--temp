from fastapi import FastAPI
import uvicorn
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from Render"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)


import alpaca_trade_api as tradeapi
import pandas as pd
import time
from ta.volatility import BollingerBands

# === CONFIGURATION ===
API_KEY = 'AKQTV2XAPAX1SYW6QEE4'
API_SECRET = 'Z6LvqE48tGCrxo2p2cUKumf5AGENRig52dcTvjbn'
BASE_URL = 'https://paper-api.alpaca.markets'
SYMBOL = 'XRPUSD'
TIMEFRAME = '5Min'
BB_PERIOD = 20
RISK_PERCENT = 0.05
TRAILING_STOP_PERCENT = 0.02
TRADE_COOLDOWN = 60 * 5  # cooldown between trades (seconds)

api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')
last_trade_time = 0

def get_data():
    bars = api.get_bars(SYMBOL, TIMEFRAME, limit=BB_PERIOD + 10).df
    df = bars[bars['symbol'] == SYMBOL].copy()
    df = df.tail(BB_PERIOD + 3)
    bb = BollingerBands(close=df['close'], window=BB_PERIOD, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    return df

def get_equity():
    account = api.get_account()
    return float(account.equity)

def get_position_qty():
    try:
        pos = api.get_position(SYMBOL)
        return float(pos.qty)
    except:
        return 0

def cancel_existing_orders():
    orders = api.list_orders(status='open')
    for order in orders:
        if order.symbol == SYMBOL:
            api.cancel_order(order.id)

def place_trailing_stop_order(qty, side, trail_percent):
    api.submit_order(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        type='trailing_stop',
        trail_percent=str(trail_percent * 100),
        time_in_force='gtc'
    )

def place_market_order(qty, side):
    api.submit_order(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        type='market',
        time_in_force='gtc'
    )

while True:
    try:
        now = time.time()
        if now - last_trade_time < TRADE_COOLDOWN:
            time.sleep(15)
            continue

        df = get_data()
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        position_qty = get_position_qty()
        equity = get_equity()
        price = latest['close']
        qty = round((equity * RISK_PERCENT) / price, 2)

        # Entry signal: Price crosses up through lower band
        if (
            prev['close'] < prev['bb_lower'] and
            latest['close'] > latest['bb_lower'] and
            position_qty == 0
        ):
            cancel_existing_orders()
            place_trailing_stop_order(qty=qty, side='buy', trail_percent=TRAILING_STOP_PERCENT)
            print(f"[BUY] {SYMBOL} Trailing Stop Entry at ~{price}")
            last_trade_time = now

        # Exit signal: Price crosses down through upper band
        elif (
            prev['close'] > prev['bb_upper'] and
            latest['close'] < latest['bb_upper'] and
            position_qty > 0
        ):
            cancel_existing_orders()
            place_market_order(qty=position_qty, side='sell')
            print(f"[SELL] {SYMBOL} exited at ~{price}")
            last_trade_time = now

        time.sleep(60)

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(60)
