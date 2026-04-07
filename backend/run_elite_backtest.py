#!/usr/bin/env python3
"""
Elite Momentum Swing Strategy

Core Insight from Backtests:
- Trailing stops work (+2.83% avg) 
- Need to enter STRONGER momentum setups
- Focus on breakout + volume surge = explosive moves

Strategy Design:
1. BREAKOUT FOCUS: Only enter stocks breaking 20-day highs
2. VOLUME SURGE: Require 2x+ average volume  
3. MOMENTUM ACCELERATION: ROC must be accelerating
4. TRAIL AGGRESSIVELY: Lock in gains quickly
5. CUT LOSERS FAST: Tight initial stop
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, '.')
from app.config import config
from nse_stocks import SECTOR_MAP


def calculate_elite_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Elite scoring for momentum breakout stocks.
    Focus on explosive setups that can deliver 5%+ in days.
    """
    df = df.copy()
    
    # === BREAKOUT SCORE (35 points) ===
    # Price relative to 20-day range
    df['range_position'] = (df['close'] - df['ll_20']) / (df['hh_20'] - df['ll_20'] + 0.001)
    df['breakout_score'] = 0
    # At or above 20-day high = maximum score
    df.loc[df['range_position'] >= 0.98, 'breakout_score'] = 35
    df.loc[(df['range_position'] >= 0.95) & (df['range_position'] < 0.98), 'breakout_score'] = 30
    df.loc[(df['range_position'] >= 0.90) & (df['range_position'] < 0.95), 'breakout_score'] = 20
    df.loc[(df['range_position'] >= 0.80) & (df['range_position'] < 0.90), 'breakout_score'] = 10
    
    # === VOLUME SURGE (25 points) ===
    df['vol_ratio'] = df['volume'] / (df['vol_ma_20'] + 1)
    df['volume_score'] = 0
    df.loc[df['vol_ratio'] >= 3.0, 'volume_score'] = 25
    df.loc[(df['vol_ratio'] >= 2.0) & (df['vol_ratio'] < 3.0), 'volume_score'] = 20
    df.loc[(df['vol_ratio'] >= 1.5) & (df['vol_ratio'] < 2.0), 'volume_score'] = 15
    df.loc[(df['vol_ratio'] >= 1.2) & (df['vol_ratio'] < 1.5), 'volume_score'] = 10
    
    # === MOMENTUM (25 points) ===
    df['roc_3'] = (df['close'] - df['close'].shift(3)) / df['close'].shift(3) * 100
    df['roc_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5) * 100
    df['momentum_score'] = 0
    # Strong recent momentum
    df.loc[df['roc_3'] > 5, 'momentum_score'] += 15
    df.loc[(df['roc_3'] > 2) & (df['roc_3'] <= 5), 'momentum_score'] += 10
    df.loc[(df['roc_3'] > 0) & (df['roc_3'] <= 2), 'momentum_score'] += 5
    # Sustained momentum
    df.loc[df['roc_5'] > 5, 'momentum_score'] += 10
    df.loc[(df['roc_5'] > 2) & (df['roc_5'] <= 5), 'momentum_score'] += 7
    df.loc[(df['roc_5'] > 0) & (df['roc_5'] <= 2), 'momentum_score'] += 3
    
    # === TREND CONFIRMATION (15 points) ===
    df['trend_score'] = 0
    df.loc[df['close'] > df['sma_20'], 'trend_score'] += 5
    df.loc[df['close'] > df['sma_50'], 'trend_score'] += 5
    df.loc[df['sma_20'] > df['sma_50'], 'trend_score'] += 5
    
    # === TOTAL SCORE ===
    df['score'] = df['breakout_score'] + df['volume_score'] + df['momentum_score'] + df['trend_score']
    
    return df


def load_data() -> pd.DataFrame:
    """Load data."""
    print("Loading data...")
    conn = sqlite3.connect(config.db_path)
    df = pd.read_sql_query("""
        SELECT e.*, i.sma_20, i.sma_50, i.rsi_14, i.atr_14, 
               i.vol_ma_20, i.hh_20, i.ll_20
        FROM eod e
        LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date >= '2020-01-01'
        ORDER BY e.symbol, e.trade_date
    """, conn)
    conn.close()
    
    print(f"Loaded {len(df):,} rows, {df['symbol'].nunique()} symbols")
    df['sector'] = df['symbol'].map(SECTOR_MAP).fillna('Unknown')
    return df


def get_fridays(df: pd.DataFrame, n_weeks: int) -> List[str]:
    """Get Friday dates."""
    dates = pd.to_datetime(df['trade_date'].unique())
    fridays = dates[dates.weekday == 4]
    return pd.Series(fridays).sort_values().iloc[-n_weeks:].dt.strftime('%Y-%m-%d').tolist()


def elite_screener(df: pd.DataFrame, date: str, top_n: int = 2) -> pd.DataFrame:
    """Run elite momentum screener."""
    historical = df[df['trade_date'] <= date].copy()
    if historical.empty:
        return pd.DataFrame()
    
    latest = historical.sort_values('trade_date').groupby('symbol').last().reset_index()
    
    # Basic filters
    latest = latest[
        (latest['close'] >= 100) &  # Higher price = more institutional interest
        (latest['sma_20'].notna()) &
        (latest['sma_50'].notna()) &
        (latest['rsi_14'].notna()) &
        (latest['atr_14'].notna()) &
        (latest['vol_ma_20'].notna()) &
        (latest['hh_20'].notna())
    ].copy()
    
    if latest.empty:
        return pd.DataFrame()
    
    latest = calculate_elite_score(latest)
    
    # ELITE FILTERS - Only the strongest setups
    filtered = latest[
        (latest['score'] >= 70) &  # High score required
        (latest['vol_ratio'] >= 1.5) &  # Volume confirmation mandatory
        (latest['roc_3'] > 0) &  # Positive 3-day momentum
        (latest['close'] > latest['sma_20']) &  # Must be in uptrend
        (latest['rsi_14'] < 80) &  # Not extremely overbought
        (latest['rsi_14'] > 40)  # Not in downtrend
    ].copy()
    
    if filtered.empty:
        return pd.DataFrame()
    
    # Trade setup - TIGHT RISK, TRAIL QUICKLY
    filtered['entry'] = filtered['close']
    
    # Tight stop: 1.2x ATR (quick cut if wrong)
    filtered['stop'] = filtered['close'] - (filtered['atr_14'] * 1.2)
    
    # Target: 6% (achievable for momentum breakouts)
    filtered['target'] = filtered['close'] * 1.06
    
    filtered['risk_pct'] = (filtered['entry'] - filtered['stop']) / filtered['entry'] * 100
    filtered['reward_pct'] = (filtered['target'] - filtered['entry']) / filtered['entry'] * 100
    
    return filtered.sort_values('score', ascending=False).head(top_n)


def simulate_momentum_trade(df: pd.DataFrame, symbol: str, entry_date: str,
                            entry: float, stop: float, target: float,
                            max_days: int = 5) -> Dict:
    """
    Aggressive momentum trade simulation.
    
    Key: Trail stop VERY quickly to lock in gains.
    Momentum trades either work fast or fail fast.
    """
    future = df[
        (df['symbol'] == symbol) & 
        (df['trade_date'] > entry_date)
    ].sort_values('trade_date').head(max_days)
    
    if future.empty:
        return {'exit_reason': 'no_data', 'exit_price': entry, 'return_pct': 0, 'bars': 0}
    
    # Entry at open with slippage
    actual_entry = future.iloc[0]['open'] * 1.002
    
    # Recalculate stop/target
    risk = entry - stop
    actual_stop = actual_entry - risk
    actual_target = actual_entry * 1.06
    
    highest = actual_entry
    trailing_active = False
    
    for idx, (_, row) in enumerate(future.iterrows()):
        bars = idx + 1
        
        # Update highest
        if row['high'] > highest:
            highest = row['high']
        
        # AGGRESSIVE TRAILING: Activate at just 1% gain
        if not trailing_active and highest >= actual_entry * 1.01:
            trailing_active = True
        
        # Calculate stop
        if trailing_active:
            # Trail at 1% below highest (very tight)
            current_stop = max(actual_stop, highest * 0.99)
        else:
            current_stop = actual_stop
        
        # Check stop
        if row['low'] <= current_stop:
            exit_price = max(current_stop, row['low'])
            return {
                'exit_reason': 'trail' if trailing_active else 'stop',
                'exit_price': exit_price,
                'return_pct': ((exit_price - actual_entry) / actual_entry) * 100,
                'bars': bars
            }
        
        # Check target
        if row['high'] >= actual_target:
            return {
                'exit_reason': 'target',
                'exit_price': actual_target,
                'return_pct': ((actual_target - actual_entry) / actual_entry) * 100,
                'bars': bars
            }
        
        # Time exit (momentum faded)
        if bars >= max_days:
            exit_price = row['close'] * 0.999
            return {
                'exit_reason': 'time',
                'exit_price': exit_price,
                'return_pct': ((exit_price - actual_entry) / actual_entry) * 100,
                'bars': bars
            }
    
    last = future.iloc[-1]['close']
    return {
        'exit_reason': 'data_end',
        'exit_price': last,
        'return_pct': ((last - actual_entry) / actual_entry) * 100,
        'bars': len(future)
    }


def run_elite_backtest(df: pd.DataFrame, weeks: int = 150, top_n: int = 2) -> Tuple[List, Dict]:
    """Run elite momentum backtest."""
    print(f"\n{'='*70}")
    print(f"  ELITE MOMENTUM STRATEGY: {weeks} weeks, Top {top_n} picks")
    print(f"{'='*70}")
    
    fridays = get_fridays(df, weeks)
    trades = []
    weekly_ret = []
    
    for i, friday in enumerate(fridays):
        cands = elite_screener(df, friday, top_n)
        
        if cands.empty:
            continue
        
        week_trades = []
        for _, row in cands.iterrows():
            result = simulate_momentum_trade(
                df, row['symbol'], friday,
                row['entry'], row['stop'], row['target']
            )
            
            trade = {
                'date': friday,
                'symbol': row['symbol'],
                'sector': row['sector'],
                'score': row['score'],
                'vol_ratio': row['vol_ratio'],
                'roc_3': row['roc_3'],
                'entry': row['entry'],
                'stop': row['stop'],
                'target': row['target'],
                'exit_price': result['exit_price'],
                'exit_reason': result['exit_reason'],
                'return_pct': result['return_pct'],
                'bars': result['bars']
            }
            trades.append(trade)
            week_trades.append(trade)
        
        if week_trades:
            weekly_ret.append({
                'date': friday,
                'trades': len(week_trades),
                'return': np.mean([t['return_pct'] for t in week_trades])
            })
        
        if (i + 1) % 30 == 0:
            print(f"  Week {i + 1}/{len(fridays)}: {len(trades)} trades so far")
    
    # Stats
    if not trades:
        return [], {'error': 'No trades'}
    
    returns = [t['return_pct'] for t in trades]
    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]
    weekly_df = pd.DataFrame(weekly_ret)
    
    exits = {}
    for t in trades:
        r = t['exit_reason']
        if r not in exits:
            exits[r] = []
        exits[r].append(t['return_pct'])
    
    stats = {
        'trades': len(trades),
        'weeks': len(weekly_ret),
        'winners': len(winners),
        'losers': len(losers),
        'win_rate': len(winners) / len(trades) * 100,
        'avg_return': np.mean(returns),
        'median': np.median(returns),
        'best': max(returns),
        'worst': min(returns),
        'std': np.std(returns),
        'avg_weekly': weekly_df['return'].mean() if not weekly_df.empty else 0,
        'weeks_profitable': (weekly_df['return'] > 0).sum() if not weekly_df.empty else 0,
        'profit_factor': sum(winners) / abs(sum(losers)) if losers else float('inf'),
        'avg_bars': np.mean([t['bars'] for t in trades]),
        'exits': {r: {'n': len(v), 'avg': np.mean(v)} for r, v in exits.items()}
    }
    
    return trades, stats


def print_elite_results(trades: List, stats: Dict):
    """Print results."""
    print("\n" + "="*70)
    print("  ELITE MOMENTUM STRATEGY RESULTS")
    print("="*70)
    
    print(f"\n  📊 TRADES: {stats['trades']} total over {stats['weeks']} weeks")
    print(f"     Winners: {stats['winners']} ({stats['win_rate']:.1f}%)")
    print(f"     Losers:  {stats['losers']}")
    
    print(f"\n  💰 RETURNS:")
    print(f"     Per Trade:    {stats['avg_return']:+.2f}% avg, {stats['median']:+.2f}% median")
    print(f"     Best/Worst:   {stats['best']:+.2f}% / {stats['worst']:+.2f}%")
    print(f"     Per Week:     {stats['avg_weekly']:+.2f}%")
    print(f"     Weeks Up:     {stats['weeks_profitable']}/{stats['weeks']}")
    
    print(f"\n  ⚖️ RISK:")
    print(f"     Profit Factor: {stats['profit_factor']:.2f}")
    print(f"     Avg Hold:      {stats['avg_bars']:.1f} days")
    
    print(f"\n  📈 EXITS:")
    for reason, data in stats['exits'].items():
        print(f"     {reason:10} n={data['n']:3}  avg={data['avg']:+.2f}%")
    
    # Assessment
    print(f"\n  {'='*70}")
    if stats['avg_weekly'] >= 5:
        print("  ✅ EXCELLENT: Hits 5%+ weekly target!")
    elif stats['avg_weekly'] >= 2:
        print("  ✅ GOOD: 2-5% weekly returns achieved")
    elif stats['avg_weekly'] >= 0:
        print("  ⚠️ MARGINAL: Profitable but below target")
    else:
        print("  ❌ LOSS: Strategy needs work")
    
    annual = (1 + stats['avg_weekly']/100) ** 52 - 1
    print(f"\n  📈 Projected Annual: {annual*100:.1f}%")
    print(f"     (From {stats['avg_weekly']:.2f}% weekly compounded)")


def main():
    print("\n" + "="*70)
    print("  ELITE MOMENTUM SWING TRADING BACKTEST")
    print("="*70)
    print(f"  Started: {datetime.now()}")
    
    df = load_data()
    
    # Main test
    trades, stats = run_elite_backtest(df, weeks=150, top_n=2)
    print_elite_results(trades, stats)
    
    # Save trades
    pd.DataFrame(trades).to_csv('elite_backtest_trades.csv', index=False)
    print(f"\n  📁 Saved to: elite_backtest_trades.csv")
    
    # Sector analysis
    if trades:
        print("\n  🏭 TOP SECTORS:")
        trades_df = pd.DataFrame(trades)
        sector_perf = trades_df.groupby('sector')['return_pct'].agg(['mean', 'count']).sort_values('mean', ascending=False)
        for sector, row in sector_perf.head(10).iterrows():
            print(f"     {sector:20} avg: {row['mean']:+.2f}%  trades: {int(row['count'])}")
    
    # Test variations
    print("\n\n" + "="*70)
    print("  TESTING VARIATIONS")
    print("="*70)
    
    for n in [3, 5]:
        _, var_stats = run_elite_backtest(df, weeks=100, top_n=n)
        print(f"\n  Top {n}: WR={var_stats['win_rate']:.1f}%, Avg={var_stats['avg_return']:+.2f}%, Weekly={var_stats['avg_weekly']:+.2f}%")


if __name__ == "__main__":
    main()
