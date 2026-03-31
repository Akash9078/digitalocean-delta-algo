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
INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d"]
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

exchange = ccxt.delta({
    'enableRateLimit': True,
})

markets = exchange.load_markets()
print(f"Loaded {len(markets)} markets from Delta Exchange\n")

results = []

for INTERVAL in INTERVALS:
    print(f"{'='*60}")
    print(f"Testing {INTERVAL} timeframe...")
    print(f"{'='*60}")
    
    try:
        all_ohlcv = []
        since = int(exchange.parse8601(start_date.isoformat()))
        now = int(exchange.milliseconds())
        
        while since < now:
            ohlcv = exchange.fetch_ohlcv(SYMBOL, INTERVAL, since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        
        if len(all_ohlcv) < 100:
            print(f"  Skipping {INTERVAL} - insufficient data ({len(all_ohlcv)} candles)")
            continue
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('datetime').sort_index()
        df = df[df.index <= pd.to_datetime(end_date)]
        
        print(f"  Loaded {len(df)} candles ({df.index[0]} to {df.index[-1]})")
        
        close = df["close"]
        
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
        
        bench_close = close
        pf_bench = vbt.Portfolio.from_holding(bench_close, init_cash=INIT_CASH, freq=INTERVAL)
        
        result = {
            'Timeframe': INTERVAL,
            'Candles': len(df),
            'Strategy Return': f"{pf.total_return()*100:.2f}%",
            'Benchmark Return': f"{pf_bench.total_return()*100:.2f}%",
            'Sharpe': f"{pf.sharpe_ratio():.2f}",
            'Max DD': f"{pf.max_drawdown()*100:.2f}%",
            'Win Rate': f"{pf.trades.win_rate()*100:.1f}%",
            'Trades': pf.trades.count(),
            'Profit Factor': f"{pf.trades.profit_factor():.2f}",
            'pf': pf,
            'pf_bench': pf_bench
        }
        results.append(result)
        
        print(f"  Strategy Return: {pf.total_return()*100:.2f}%")
        print(f"  Benchmark Return: {pf_bench.total_return()*100:.2f}%")
        print(f"  Max Drawdown: {pf.max_drawdown()*100:.2f}%")
        print(f"  Trades: {pf.trades.count()}, Win Rate: {pf.trades.win_rate()*100:.1f}%")
        print()
        
    except Exception as e:
        print(f"  Error: {e}")
        continue

print(f"\n{'='*80}")
print("ALL TIMEFRAMES COMPARISON")
print(f"{'='*80}\n")

comparison_df = pd.DataFrame([{
    'Timeframe': r['Timeframe'],
    'Candles': r['Candles'],
    'Strategy Return': r['Strategy Return'],
    'Benchmark Return': r['Benchmark Return'],
    'Sharpe': r['Sharpe'],
    'Max DD': r['Max DD'],
    'Win Rate': r['Win Rate'],
    'Trades': r['Trades'],
    'Profit Factor': r['Profit Factor']
} for r in results])

print(comparison_df.to_string(index=False))

positive_results = [r for r in results if float(r['Strategy Return'].replace('%','')) > 0]
if positive_results:
    print(f"\n{'='*80}")
    print("BEST PERFORMING TIMEFRAMES (Positive Return)")
    print(f"{'='*80}\n")
    for r in sorted(positive_results, key=lambda x: float(x['Strategy Return'].replace('%','')), reverse=True):
        print(f"  {r['Timeframe']}: {r['Strategy Return']} | Sharpe: {r['Sharpe']} | Max DD: {r['Max DD']} | Trades: {r['Trades']}")

best_sharpe = max(results, key=lambda x: x['pf'].sharpe_ratio() if x['pf'].sharpe_ratio() > -100 else -100)
print(f"\nBest Risk-Adjusted: {best_sharpe['Timeframe']} (Sharpe: {best_sharpe['Sharpe']})")

min_dd = min(results, key=lambda x: x['pf'].max_drawdown())
print(f"Lowest Drawdown: {min_dd['Timeframe']} (Max DD: {min_dd['Max DD']})")

print(f"\n{'='*80}")
print("Recommendation")
print(f"{'='*80}")
if positive_results:
    best = max(positive_results, key=lambda x: float(x['Strategy Return'].replace('%','')))
    print(f"Best overall: {best['Timeframe']} with {best['Strategy Return']} return")
else:
    print("No positive returns across timeframes - strategy needs parameter tuning")
