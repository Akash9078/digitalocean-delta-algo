import os
from datetime import datetime, timedelta
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd
import talib as tl
import vectorbt as vbt
from dotenv import find_dotenv, load_dotenv

try:
    from openalgo import ta
    exrem = ta.exrem
except ImportError:
    def exrem(s1, s2):
        result = s1.copy()
        active = False
        for i in range(len(s1)):
            if active:
                result.iloc[i] = False
            if s1.iloc[i] and not active:
                active = True
            if s2.iloc[i]:
                active = False
        return result

script_dir = Path(__file__).resolve().parent
load_dotenv(find_dotenv(), override=False)

SYMBOL = "BTC/USDT"
INTERVAL = "5m"
INIT_CASH = 1_000_000
FEES = 0.0004
FIXED_FEES = 0

SMA_SHORT = 9
SMA_LONG = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

start_date = datetime.now() - timedelta(days=180)
end_date = datetime.now()

print(f"Fetching {SYMBOL} data from Delta Exchange...")
exchange = ccxt.delta({
    'enableRateLimit': True,
})

markets = exchange.load_markets()
print(f"Available markets: {len(markets)}")

if SYMBOL not in markets:
    print(f"Symbol {SYMBOL} not found. Available BTC markets:")
    for sym in markets:
        if 'BTC' in sym:
            print(f"  - {sym}")

print(f"Fetching OHLCV for {SYMBOL} timeframe {INTERVAL}...")

all_ohlcv = []
since = int(exchange.parse8601(start_date.isoformat()))
now = int(exchange.milliseconds())

while since < now:
    ohlcv = exchange.fetch_ohlcv(SYMBOL, INTERVAL, since, limit=1000)
    if not ohlcv:
        break
    all_ohlcv.extend(ohlcv)
    since = ohlcv[-1][0] + 1
    print(f"  Fetched {len(all_ohlcv)} candles...")

df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
df = df.set_index('datetime').sort_index()
df = df[df.index <= pd.to_datetime(end_date)]

print(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")

close = df["close"]
high = df["high"]
low = df["low"]

short_sma = pd.Series(tl.SMA(close.values, timeperiod=SMA_SHORT), index=close.index)
long_sma = pd.Series(tl.SMA(close.values, timeperiod=SMA_LONG), index=close.index)
rsi = pd.Series(tl.RSI(close.values, timeperiod=RSI_PERIOD), index=close.index)

short_prev = short_sma.shift(1)
long_prev = long_sma.shift(1)
short_curr = short_sma.shift(0)
long_curr = long_sma.shift(0)

golden_cross = (short_prev <= long_prev) & (short_curr > long_curr)
death_cross = (short_prev >= long_prev) & (short_curr < long_curr)

rsi_buy_ok = rsi < RSI_OVERBOUGHT
rsi_sell_ok = rsi > RSI_OVERSOLD

buy_raw = golden_cross & rsi_buy_ok
sell_raw = death_cross & rsi_sell_ok

entries = exrem(buy_raw.fillna(False), sell_raw.fillna(False))
exits = exrem(sell_raw.fillna(False), buy_raw.fillna(False))

pf = vbt.Portfolio.from_signals(
    close, entries, exits,
    init_cash=INIT_CASH, size=1.0, size_type="percent",
    fees=FEES, fixed_fees=FIXED_FEES, direction="longonly",
    freq=INTERVAL,
)

bench_symbol = "BTC/USDT"
bench_ohlcv = []
since = int(exchange.parse8601(start_date.isoformat()))
now = int(exchange.milliseconds())
while since < now:
    ohlcv = exchange.fetch_ohlcv(bench_symbol, INTERVAL, since, limit=1000)
    if not ohlcv:
        break
    bench_ohlcv.extend(ohlcv)
    since = bench_ohlcv[-1][0] + 1

bench_df = pd.DataFrame(bench_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
bench_df['datetime'] = pd.to_datetime(bench_df['timestamp'], unit='ms')
bench_df = bench_df.set_index('datetime').sort_index()
bench_close = bench_df["close"].reindex(close.index).ffill().bfill()
pf_bench = vbt.Portfolio.from_holding(bench_close, init_cash=INIT_CASH, freq=INTERVAL)

print("\n" + "="*60)
print("STRATEGY PERFORMANCE")
print("="*60)
print(f"Total Return: {pf.total_return()*100:.2f}%")
print(f"Sharpe Ratio: {pf.sharpe_ratio():.2f}")
print(f"Sortino Ratio: {pf.sortino_ratio():.2f}")
print(f"Max Drawdown: {pf.max_drawdown()*100:.2f}%")
print(f"Win Rate: {pf.trades.win_rate()*100:.1f}%")
print(f"Total Trades: {pf.trades.count()}")
print(f"Profit Factor: {pf.trades.profit_factor():.2f}")

print("\n" + "="*60)
print("BENCHMARK (Buy & Hold BTC/USDT)")
print("="*60)
print(f"Total Return: {pf_bench.total_return()*100:.2f}%")
print(f"Sharpe Ratio: {pf_bench.sharpe_ratio():.2f}")
print(f"Max Drawdown: {pf_bench.max_drawdown()*100:.2f}%")

print("\n" + "="*60)
print("STRATEGY vs BENCHMARK COMPARISON")
print("="*60)
comparison = pd.DataFrame({
    "SMA+RSI Strategy": [
        f"{pf.total_return()*100:.2f}%", f"{pf.sharpe_ratio():.2f}",
        f"{pf.sortino_ratio():.2f}", f"{pf.max_drawdown()*100:.2f}%",
        f"{pf.trades.win_rate()*100:.1f}%", f"{pf.trades.count()}",
        f"{pf.trades.profit_factor():.2f}",
    ],
    "BTC/USDT Buy & Hold": [
        f"{pf_bench.total_return()*100:.2f}%", f"{pf_bench.sharpe_ratio():.2f}",
        f"{pf_bench.sortino_ratio():.2f}", f"{pf_bench.max_drawdown()*100:.2f}%",
        "-", "-", "-",
    ],
}, index=["Total Return", "Sharpe Ratio", "Sortino Ratio", "Max Drawdown", "Win Rate", "Total Trades", "Profit Factor"])
print(comparison.to_string())

print("\n" + "="*60)
print("Plain Language Summary")
print("="*60)
print(f"* Strategy returned {pf.total_return()*100:.2f}% vs buy-hold {pf_bench.total_return()*100:.2f}%")
print(f"* Max drawdown: {pf.max_drawdown()*100:.2f}% (strategy) vs {pf_bench.max_drawdown()*100:.2f}% (benchmark)")
print(f"* On Rs {INIT_CASH:,}, worst loss = Rs {abs(pf.max_drawdown()) * INIT_CASH:,.0f}")

pf.positions.records_readable.to_csv(script_dir / "backtest_trades.csv", index=False)
print(f"\nTrades saved to: {script_dir / 'backtest_trades.csv'}")

print("\n[Chart disabled - use Jupyter for visualization]")
