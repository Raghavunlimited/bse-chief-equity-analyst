#!/usr/bin/env python3
"""
Optimized Swing Trading Strategy for 5-7% Weekly Returns

Based on backtest analysis, key optimizations:
1. Wider stop loss (2x ATR) - reduce premature stops
2. More achievable targets (4-5%) - higher hit rate
3. Trailing stop mechanism - lock in profits
4. Better entry criteria - momentum + pullback
5. Sector filtering - focus on top performing sectors
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, '.')
from app.config import config
from nse_stocks import SECTOR_MAP


# Top performing sectors from initial backtest
TOP_SECTORS = ['IT', 'Auto Ancillary', 'Power', 'Energy', 'Consumer Durables', 
               'Pharma', 'Banking', 'Financial Services', 'Capital Goods', 
               'Chemicals', 'Textiles', 'Insurance', 'FMCG']


def calculate_optimized_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimized scoring focused on momentum continuation with pullback entries.
    
    Key changes from original:
    - More weight on trend strength
    - Pullback entry (not buying at highs)
    - Volume confirmation
    - Momentum acceleration
    """
    df = df.copy()
    
    # Initialize scores
    df['score'] = 0
    
    # 1. TREND SCORE (25 points) - Strong uptrend is key
    df['trend_score'] = 0
    df.loc[df['close'] > df['sma_50'], 'trend_score'] += 8
    df.loc[df['close'] > df['sma_20'], 'trend_score'] += 5
    df.loc[df['sma_20'] > df['sma_50'], 'trend_score'] += 7
    # 20-day MA rising
    df.loc[df['sma_20'] > df['sma_20'].shift(5), 'trend_score'] += 5
    
    # 2. PULLBACK ENTRY (25 points) - Buy on dips, not at peaks
    # Ideal: price pulled back from recent high but still in uptrend
    df['pullback_pct'] = (df['hh_20'] - df['close']) / df['hh_20'] * 100
    df['pullback_score'] = 0
    # Sweet spot: 3-8% pullback from high
    df.loc[(df['pullback_pct'] >= 3) & (df['pullback_pct'] <= 8), 'pullback_score'] = 25
    df.loc[(df['pullback_pct'] > 1) & (df['pullback_pct'] < 3), 'pullback_score'] = 15
    df.loc[(df['pullback_pct'] > 8) & (df['pullback_pct'] <= 12), 'pullback_score'] = 15
    df.loc[df['pullback_pct'] < 1, 'pullback_score'] = 5  # Too close to high = risky
    
    # 3. RSI SCORE (15 points) - Not overbought, constructive zone
    df['rsi_score'] = 0
    df.loc[(df['rsi_14'] >= 45) & (df['rsi_14'] <= 60), 'rsi_score'] = 15  # Sweet spot
    df.loc[(df['rsi_14'] > 60) & (df['rsi_14'] <= 65), 'rsi_score'] = 10
    df.loc[(df['rsi_14'] >= 40) & (df['rsi_14'] < 45), 'rsi_score'] = 8
    
    # 4. MOMENTUM SCORE (20 points) - Confirms strength
    df['roc_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5) * 100
    df['roc_20'] = (df['close'] - df['close'].shift(20)) / df['close'].shift(20) * 100
    df['momentum_score'] = 0
    # Positive short-term momentum
    df.loc[df['roc_5'] > 0, 'momentum_score'] += 5
    df.loc[df['roc_5'] > 2, 'momentum_score'] += 5
    # Positive medium-term momentum
    df.loc[df['roc_20'] > 0, 'momentum_score'] += 5
    df.loc[df['roc_20'] > 5, 'momentum_score'] += 5
    
    # 5. VOLUME SCORE (15 points) - Institutional interest
    df['vol_ratio'] = df['volume'] / (df['vol_ma_20'] + 1)
    df['volume_score'] = 0
    df.loc[df['vol_ratio'] > 1.5, 'volume_score'] = 15
    df.loc[(df['vol_ratio'] > 1.2) & (df['vol_ratio'] <= 1.5), 'volume_score'] = 10
    df.loc[(df['vol_ratio'] > 0.8) & (df['vol_ratio'] <= 1.2), 'volume_score'] = 5
    
    # Total score (max 100)
    df['score'] = (df['trend_score'] + df['pullback_score'] + df['rsi_score'] + 
                   df['momentum_score'] + df['volume_score'])
    
    return df


def load_data() -> pd.DataFrame:
    """Load historical data with indicators."""
    print("Loading historical data...")
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
    
    print(f"Loaded {len(df):,} rows for {df['symbol'].nunique()} symbols")
    df['sector'] = df['symbol'].map(SECTOR_MAP).fillna('Unknown')
    
    return df


def get_fridays(df: pd.DataFrame, num_weeks: int = 150) -> List[str]:
    """Get Friday screening dates."""
    dates = pd.to_datetime(df['trade_date'].unique())
    fridays = dates[dates.weekday == 4]
    fridays = pd.Series(fridays).sort_values()
    return fridays.iloc[-num_weeks:].dt.strftime('%Y-%m-%d').tolist()


def run_optimized_screener(df: pd.DataFrame, date: str, top_n: int = 2) -> pd.DataFrame:
    """
    Optimized screener with pullback entry and sector filtering.
    """
    # Get data up to screening date
    historical = df[df['trade_date'] <= date].copy()
    if historical.empty:
        return pd.DataFrame()
    
    # Latest data per symbol
    latest = historical.sort_values('trade_date').groupby('symbol').last().reset_index()
    
    # Minimum data requirements
    latest = latest[
        (latest['close'] >= 50) &
        (latest['sma_20'].notna()) &
        (latest['sma_50'].notna()) &
        (latest['rsi_14'].notna()) &
        (latest['atr_14'].notna()) &
        (latest['vol_ma_20'].notna()) &
        (latest['hh_20'].notna())
    ].copy()
    
    if latest.empty:
        return pd.DataFrame()
    
    # Calculate scores
    latest = calculate_optimized_score(latest)
    
    # Apply filters
    filtered = latest[
        (latest['score'] >= 55) &  # Min score
        (latest['rsi_14'] < 70) &  # Not overbought
        (latest['rsi_14'] > 40) &  # Not oversold
        (latest['close'] > latest['sma_50']) &  # Uptrend
        (latest['close'] > latest['sma_20']) &  # Short-term uptrend
        (latest['sector'].isin(TOP_SECTORS + ['Unknown'])) &  # Good sectors
        (latest['vol_ratio'] >= 0.7)  # Minimum liquidity
    ].copy()
    
    if filtered.empty:
        return pd.DataFrame()
    
    # Calculate trade parameters - OPTIMIZED
    filtered['entry_price'] = filtered['close']
    
    # WIDER STOP: 2x ATR for swing trades (was 1.5x)
    filtered['stop_loss'] = filtered['close'] - (filtered['atr_14'] * 2.0)
    
    # ACHIEVABLE TARGET: Aim for 5% target (more realistic)
    # With 2x ATR stop (~3-4% risk), this gives ~1.5:1 R:R but higher hit rate
    filtered['target_price'] = filtered['close'] * 1.05  # 5% fixed target
    
    # Ensure minimum risk-reward of 1:1
    risk = filtered['entry_price'] - filtered['stop_loss']
    reward = filtered['target_price'] - filtered['entry_price']
    # If R:R < 1, use 1.5x risk as target
    low_rr_mask = (reward / risk) < 1
    filtered.loc[low_rr_mask, 'target_price'] = filtered.loc[low_rr_mask, 'entry_price'] + (risk[low_rr_mask] * 1.5)
    
    filtered['risk_pct'] = (filtered['entry_price'] - filtered['stop_loss']) / filtered['entry_price'] * 100
    filtered['reward_pct'] = (filtered['target_price'] - filtered['entry_price']) / filtered['entry_price'] * 100
    
    # Sort by score
    filtered = filtered.sort_values('score', ascending=False).head(top_n)
    
    return filtered


def simulate_trade_with_trailing(df: pd.DataFrame, symbol: str, entry_date: str,
                                  entry_price: float, stop_loss: float, target_price: float,
                                  max_days: int = 7) -> Dict:
    """
    Enhanced trade simulation with trailing stop mechanism.
    
    Key improvements:
    - Trailing stop after 2% profit
    - Shorter holding period (7 days for swing)
    - Realistic slippage
    """
    future = df[
        (df['symbol'] == symbol) & (df['trade_date'] > entry_date)
    ].sort_values('trade_date').head(max_days)
    
    if future.empty:
        return {'exit_reason': 'no_data', 'exit_price': entry_price, 'return_pct': 0, 'bars_held': 0}
    
    # Entry at Monday open with slippage
    first_day = future.iloc[0]
    actual_entry = first_day['open'] * 1.003  # 0.3% slippage
    
    # Recalculate stop/target based on actual entry
    original_risk = entry_price - stop_loss
    actual_stop = actual_entry - original_risk
    actual_target = actual_entry + (entry_price * 0.05)  # 5% target from actual entry
    
    # Track highest price for trailing stop
    highest_price = actual_entry
    trailing_activated = False
    
    for idx, (_, row) in enumerate(future.iterrows()):
        bars_held = idx + 1
        
        # Update highest price
        if row['high'] > highest_price:
            highest_price = row['high']
        
        # Activate trailing stop after 2% gain
        if not trailing_activated and highest_price >= actual_entry * 1.02:
            trailing_activated = True
        
        # Calculate current stop (trailing or fixed)
        if trailing_activated:
            # Trail stop at 1.5% below highest price
            current_stop = max(actual_stop, highest_price * 0.985)
        else:
            current_stop = actual_stop
        
        # Check stop loss
        if row['low'] <= current_stop:
            exit_price = max(current_stop, row['low'])  # Can't exit below low
            return {
                'exit_reason': 'trailing_stop' if trailing_activated else 'stop_loss',
                'exit_price': exit_price,
                'return_pct': ((exit_price - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
        
        # Check target
        if row['high'] >= actual_target:
            return {
                'exit_reason': 'target',
                'exit_price': actual_target,
                'return_pct': ((actual_target - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
        
        # Time exit
        if bars_held >= max_days:
            exit_price = row['close'] * 0.998  # Slippage
            return {
                'exit_reason': 'time_exit',
                'exit_price': exit_price,
                'return_pct': ((exit_price - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
    
    # End of data
    last = future.iloc[-1]['close']
    return {
        'exit_reason': 'data_end',
        'exit_price': last,
        'return_pct': ((last - actual_entry) / actual_entry) * 100,
        'bars_held': len(future),
        'actual_entry': actual_entry
    }


def run_optimized_backtest(df: pd.DataFrame, num_weeks: int = 150, top_n: int = 2) -> Tuple[List, Dict]:
    """Run the optimized backtest."""
    print(f"\n{'='*60}")
    print(f"OPTIMIZED STRATEGY BACKTEST: {num_weeks} weeks, Top {top_n} picks")
    print(f"{'='*60}\n")
    
    fridays = get_fridays(df, num_weeks)
    trades = []
    weekly_returns = []
    
    for i, friday in enumerate(fridays):
        candidates = run_optimized_screener(df, friday, top_n)
        
        if candidates.empty:
            continue
        
        week_trades = []
        for _, row in candidates.iterrows():
            result = simulate_trade_with_trailing(
                df, row['symbol'], friday,
                row['entry_price'], row['stop_loss'], row['target_price']
            )
            
            trade = {
                'date': friday,
                'symbol': row['symbol'],
                'sector': row['sector'],
                'score': row['score'],
                'entry': row['entry_price'],
                'stop': row['stop_loss'],
                'target': row['target_price'],
                'exit_price': result['exit_price'],
                'exit_reason': result['exit_reason'],
                'return_pct': result['return_pct'],
                'bars_held': result['bars_held']
            }
            trades.append(trade)
            week_trades.append(trade)
        
        if week_trades:
            weekly_returns.append({
                'date': friday,
                'trades': len(week_trades),
                'avg_return': np.mean([t['return_pct'] for t in week_trades])
            })
        
        if (i + 1) % 25 == 0:
            print(f"  Processed {i + 1}/{len(fridays)} weeks...")
    
    # Calculate stats
    stats = calculate_stats(trades, weekly_returns)
    return trades, stats


def calculate_stats(trades: List, weekly: List) -> Dict:
    """Calculate backtest statistics."""
    if not trades:
        return {'error': 'No trades'}
    
    returns = [t['return_pct'] for t in trades]
    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]
    
    weekly_df = pd.DataFrame(weekly)
    
    stats = {
        'total_trades': len(trades),
        'total_weeks': len(weekly),
        'winning': len(winners),
        'losing': len(losers),
        'win_rate': len(winners) / len(trades) * 100,
        'avg_return': np.mean(returns),
        'median_return': np.median(returns),
        'best': max(returns),
        'worst': min(returns),
        'std': np.std(returns),
        'avg_weekly': weekly_df['avg_return'].mean() if not weekly_df.empty else 0,
        'weeks_profitable': (weekly_df['avg_return'] > 0).sum() if not weekly_df.empty else 0,
        'profit_factor': sum(winners) / abs(sum(losers)) if losers else float('inf'),
        'target_rate': len([t for t in trades if t['exit_reason'] == 'target']) / len(trades) * 100,
        'stop_rate': len([t for t in trades if 'stop' in t['exit_reason']]) / len(trades) * 100,
        'avg_bars': np.mean([t['bars_held'] for t in trades])
    }
    
    # Exit breakdown
    exit_types = {}
    for t in trades:
        reason = t['exit_reason']
        if reason not in exit_types:
            exit_types[reason] = []
        exit_types[reason].append(t['return_pct'])
    
    stats['exits'] = {r: {'count': len(v), 'avg': np.mean(v)} for r, v in exit_types.items()}
    
    return stats


def print_results(trades: List, stats: Dict):
    """Print backtest results."""
    print("\n" + "="*60)
    print("OPTIMIZED STRATEGY RESULTS")
    print("="*60)
    
    print(f"\n📊 TRADE STATISTICS:")
    print(f"   Total Trades:       {stats['total_trades']}")
    print(f"   Winning Trades:     {stats['winning']} ({stats['win_rate']:.1f}%)")
    print(f"   Losing Trades:      {stats['losing']}")
    
    print(f"\n💰 RETURN METRICS:")
    print(f"   Avg Return/Trade:   {stats['avg_return']:+.2f}%")
    print(f"   Median Return:      {stats['median_return']:+.2f}%")
    print(f"   Best Trade:         {stats['best']:+.2f}%")
    print(f"   Worst Trade:        {stats['worst']:+.2f}%")
    
    print(f"\n📅 WEEKLY PERFORMANCE:")
    print(f"   Avg Weekly Return:  {stats['avg_weekly']:+.2f}%")
    print(f"   Profitable Weeks:   {stats['weeks_profitable']} / {stats['total_weeks']}")
    weekly_wr = stats['weeks_profitable'] / stats['total_weeks'] * 100 if stats['total_weeks'] > 0 else 0
    print(f"   Weekly Win Rate:    {weekly_wr:.1f}%")
    
    print(f"\n🎯 EXIT ANALYSIS:")
    print(f"   Target Hit Rate:    {stats['target_rate']:.1f}%")
    print(f"   Stop Hit Rate:      {stats['stop_rate']:.1f}%")
    print(f"   Avg Holding:        {stats['avg_bars']:.1f} days")
    print(f"   Profit Factor:      {stats['profit_factor']:.2f}")
    
    print(f"\n📈 EXIT BREAKDOWN:")
    for reason, data in stats['exits'].items():
        print(f"   {reason:15} Count: {data['count']:4}  Avg: {data['avg']:+.2f}%")
    
    # Strategy assessment
    print(f"\n{'='*60}")
    print("STRATEGY ASSESSMENT")
    print("="*60)
    
    if stats['avg_weekly'] >= 5:
        print("✅ EXCELLENT: Achieves 5%+ weekly target!")
    elif stats['avg_weekly'] >= 2:
        print("✅ GOOD: Achieves 2-5% weekly returns.")
    elif stats['avg_weekly'] >= 0:
        print("⚠️ MARGINAL: Profitable but below target.")
    else:
        print("❌ NEEDS WORK: Strategy losing money.")
    
    # Projected annual return
    annual = (1 + stats['avg_weekly']/100) ** 52 - 1
    print(f"\n📈 Projected Annual Return: {annual*100:.1f}%")
    print(f"   (Based on {stats['avg_weekly']:.2f}% weekly compounded)")


def main():
    print("\n" + "="*60)
    print("OPTIMIZED SWING TRADING STRATEGY BACKTEST")
    print("="*60)
    print(f"Started: {datetime.now()}")
    
    df = load_data()
    
    # Run optimized backtest
    trades, stats = run_optimized_backtest(df, num_weeks=150, top_n=2)
    print_results(trades, stats)
    
    # Save results
    pd.DataFrame(trades).to_csv('optimized_backtest_trades.csv', index=False)
    print(f"\n📁 Saved trades to: optimized_backtest_trades.csv")
    
    # Test variations
    print("\n\n" + "="*60)
    print("TESTING STRATEGY VARIATIONS")
    print("="*60)
    
    variations = [
        {'top_n': 3, 'label': 'Top 3 picks'},
        {'top_n': 5, 'label': 'Top 5 picks'},
    ]
    
    for var in variations:
        print(f"\n--- {var['label']} ---")
        _, var_stats = run_optimized_backtest(df, num_weeks=100, top_n=var['top_n'])
        print(f"   Win Rate: {var_stats['win_rate']:.1f}%")
        print(f"   Avg Return: {var_stats['avg_return']:+.2f}%")
        print(f"   Avg Weekly: {var_stats['avg_weekly']:+.2f}%")
        print(f"   Target Rate: {var_stats['target_rate']:.1f}%")


if __name__ == "__main__":
    main()
