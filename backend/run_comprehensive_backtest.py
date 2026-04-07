#!/usr/bin/env python3
"""
Comprehensive Swing Trading Strategy Backtest

This script runs multi-year backtests to validate and optimize the swing trading strategy
for achieving 5-7% weekly returns on top 2 picks.

Key Strategy Elements:
1. Ultimate Screener scoring (patterns, trend, volume, momentum)
2. ATR-based stop loss and targets
3. Weekly stock selection (Fridays for next week execution)
4. Position sizing based on 2% risk per trade
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import sys
import warnings
warnings.filterwarnings('ignore')

# Add app to path
sys.path.insert(0, '.')
from app.config import config
from nse_stocks import SECTOR_MAP


def calculate_backtest_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Simplified scoring for backtest that works with available columns.
    Score components:
    1. Trend (close > SMA50, SMA20 > SMA50) - 20 points
    2. RSI in sweet spot (45-65) - 15 points
    3. Near 20-day high (breakout potential) - 20 points
    4. Volume confirmation - 15 points
    5. ROC momentum - 15 points
    6. Risk/Reward setup - 15 points
    """
    df = df.copy()
    df['score'] = 0
    
    # 1. Trend Score (20 points)
    df['trend_score'] = 0
    df.loc[df['close'] > df['sma_50'], 'trend_score'] += 10
    df.loc[df['close'] > df['sma_20'], 'trend_score'] += 5
    df.loc[df['sma_20'] > df['sma_50'], 'trend_score'] += 5
    
    # 2. RSI Score (15 points)
    df['rsi_score'] = 0
    df.loc[(df['rsi_14'] > 45) & (df['rsi_14'] < 65), 'rsi_score'] = 15
    df.loc[(df['rsi_14'] >= 55) & (df['rsi_14'] <= 60), 'rsi_score'] = 15  # Sweet spot
    df.loc[(df['rsi_14'] >= 40) & (df['rsi_14'] < 45), 'rsi_score'] = 10
    df.loc[(df['rsi_14'] > 65) & (df['rsi_14'] < 70), 'rsi_score'] = 8
    
    # 3. Breakout Score (20 points) - close near 20-day high
    df['breakout_pct'] = (df['close'] - df['ll_20']) / (df['hh_20'] - df['ll_20'] + 0.0001)
    df['breakout_score'] = 0
    df.loc[df['breakout_pct'] > 0.95, 'breakout_score'] = 20  # Within 5% of high
    df.loc[(df['breakout_pct'] > 0.85) & (df['breakout_pct'] <= 0.95), 'breakout_score'] = 15
    df.loc[(df['breakout_pct'] > 0.70) & (df['breakout_pct'] <= 0.85), 'breakout_score'] = 10
    
    # 4. Volume Score (15 points)
    df['vol_ratio'] = df['volume'] / (df['vol_ma_20'] + 1)
    df['volume_score'] = 0
    df.loc[df['vol_ratio'] > 2.0, 'volume_score'] = 15
    df.loc[(df['vol_ratio'] > 1.5) & (df['vol_ratio'] <= 2.0), 'volume_score'] = 12
    df.loc[(df['vol_ratio'] > 1.0) & (df['vol_ratio'] <= 1.5), 'volume_score'] = 8
    
    # 5. ROC Momentum (15 points) - 5 and 10 day rate of change
    df['roc_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5) * 100
    df['roc_10'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10) * 100
    df['momentum_score'] = 0
    df.loc[df['roc_5'] > 3, 'momentum_score'] += 8
    df.loc[(df['roc_5'] > 0) & (df['roc_5'] <= 3), 'momentum_score'] += 5
    df.loc[df['roc_10'] > 5, 'momentum_score'] += 7
    df.loc[(df['roc_10'] > 0) & (df['roc_10'] <= 5), 'momentum_score'] += 4
    
    # 6. Risk/Reward Setup (ATR-based) - good risk/reward potential
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    df['rr_score'] = 0
    df.loc[(df['atr_pct'] > 2) & (df['atr_pct'] < 5), 'rr_score'] = 15  # Ideal volatility
    df.loc[(df['atr_pct'] >= 1.5) & (df['atr_pct'] <= 2), 'rr_score'] = 12
    df.loc[(df['atr_pct'] >= 5) & (df['atr_pct'] <= 7), 'rr_score'] = 8
    
    # Total score
    df['score'] = (df['trend_score'] + df['rsi_score'] + df['breakout_score'] + 
                   df['volume_score'] + df['momentum_score'] + df['rr_score'])
    
    return df


def load_all_data() -> pd.DataFrame:
    """Load all EOD data with indicators."""
    print("Loading historical data...")
    conn = sqlite3.connect(config.db_path)
    
    # Load EOD data
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
    print(f"Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
    
    # Add sector mapping
    df['sector'] = df['symbol'].map(SECTOR_MAP).fillna('Unknown')
    
    return df


def get_screening_dates(df: pd.DataFrame, num_weeks: int = 200) -> List[str]:
    """Get weekly screening dates (Fridays)."""
    dates = pd.to_datetime(df['trade_date'].unique())
    dates = pd.Series(dates).sort_values()
    
    # Filter to Fridays (weekday=4)
    fridays = dates[dates.dt.weekday == 4]
    
    # Get last N weeks
    return fridays.iloc[-num_weeks:].dt.strftime('%Y-%m-%d').tolist()


def run_screener_for_date(df: pd.DataFrame, screening_date: str, top_n: int = 5) -> pd.DataFrame:
    """
    Run the ultimate screener for a specific date.
    Returns top candidates with entry/stop/target.
    """
    # Filter data up to screening date
    mask = df['trade_date'] <= screening_date
    historical = df[mask].copy()
    
    if historical.empty:
        return pd.DataFrame()
    
    # Get latest data per symbol (the screening date)
    latest = historical.sort_values('trade_date').groupby('symbol').last().reset_index()
    
    # Filter for minimum requirements
    latest = latest[
        (latest['close'] >= 50) &  # Min price
        (latest['volume'] > 0) &
        (latest['sma_20'].notna()) &
        (latest['sma_50'].notna()) &
        (latest['rsi_14'].notna()) &
        (latest['atr_14'].notna()) &
        (latest['vol_ma_20'].notna()) &
        (latest['hh_20'].notna())
    ].copy()
    
    if latest.empty:
        return pd.DataFrame()
    
    # Calculate score using our backtest scoring
    latest = calculate_backtest_score(latest)
    
    # Apply core filters
    filtered = latest[
        (latest['score'] >= 50) &  # Min score (out of 100)
        (latest['rsi_14'] < 75) &  # Not overbought
        (latest['rsi_14'] > 35) &  # Not oversold (may bounce)
        (latest['close'] > latest['sma_50']) &  # Above 50 MA
        (latest['close'] > latest['sma_20']) &  # Above 20 MA (confirming trend)
        (latest['volume'] >= latest['vol_ma_20'] * 0.8)  # Decent volume
    ].copy()
    
    if filtered.empty:
        return pd.DataFrame()
    
    # Calculate entry, stop, target
    filtered['entry_price'] = filtered['close']
    
    # ATR-based stop (1.5x ATR for swing trades)
    filtered['stop_loss'] = filtered['close'] - (filtered['atr_14'] * 1.5)
    
    # Target for 5-7% (aim for 2.5x risk-reward)
    risk = filtered['entry_price'] - filtered['stop_loss']
    filtered['target_price'] = filtered['entry_price'] + (risk * 2.5)
    
    # Calculate risk and reward percentages
    filtered['risk_pct'] = (filtered['entry_price'] - filtered['stop_loss']) / filtered['entry_price'] * 100
    filtered['reward_pct'] = (filtered['target_price'] - filtered['entry_price']) / filtered['entry_price'] * 100
    
    # Sort by score and take top N
    filtered = filtered.sort_values('score', ascending=False).head(top_n)
    
    return filtered[['symbol', 'sector', 'close', 'entry_price', 'stop_loss', 'target_price', 
                     'risk_pct', 'reward_pct', 'score', 'rsi_14', 'atr_14',
                     'trend_score', 'breakout_score', 'volume_score', 'momentum_score']]


def simulate_trade(df: pd.DataFrame, symbol: str, entry_date: str, 
                   entry_price: float, stop_loss: float, target_price: float,
                   max_holding_days: int = 10) -> Dict:
    """
    Simulate a single trade with realistic execution.
    Entry on Monday open after Friday screening.
    """
    # Get future prices after entry date
    future_data = df[
        (df['symbol'] == symbol) &
        (df['trade_date'] > entry_date)
    ].sort_values('trade_date').head(max_holding_days)
    
    if future_data.empty:
        return {
            'exit_reason': 'no_data',
            'exit_price': entry_price,
            'return_pct': 0,
            'bars_held': 0
        }
    
    # Monday open entry (slippage of 0.5%)
    first_day = future_data.iloc[0]
    actual_entry = first_day['open'] * 1.005  # 0.5% slippage
    
    # Recalculate stop and target based on actual entry
    original_risk = entry_price - stop_loss
    actual_stop = actual_entry - original_risk
    actual_target = actual_entry + (original_risk * 2.5)
    
    # Simulate day by day
    for idx, (_, row) in enumerate(future_data.iterrows()):
        bars_held = idx + 1
        
        # Check stop loss (intraday low)
        if row['low'] <= actual_stop:
            return {
                'exit_reason': 'stop_loss',
                'exit_price': actual_stop,
                'return_pct': ((actual_stop - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
        
        # Check target (intraday high)
        if row['high'] >= actual_target:
            return {
                'exit_reason': 'target',
                'exit_price': actual_target,
                'return_pct': ((actual_target - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
        
        # Time-based exit after max days
        if bars_held >= max_holding_days:
            exit_price = row['close'] * 0.998  # 0.2% slippage on exit
            return {
                'exit_reason': 'time_exit',
                'exit_price': exit_price,
                'return_pct': ((exit_price - actual_entry) / actual_entry) * 100,
                'bars_held': bars_held,
                'actual_entry': actual_entry
            }
    
    # Default: close at last available price
    last_close = future_data.iloc[-1]['close']
    return {
        'exit_reason': 'data_end',
        'exit_price': last_close,
        'return_pct': ((last_close - actual_entry) / actual_entry) * 100,
        'bars_held': len(future_data),
        'actual_entry': actual_entry
    }


def run_backtest(df: pd.DataFrame, num_weeks: int = 150, top_n: int = 2) -> Tuple[List[Dict], Dict]:
    """
    Run full backtest over multiple weeks.
    
    Strategy: Every Friday, screen for top N stocks. Enter Monday, exit when target/stop hit or 10 days.
    """
    print(f"\n{'='*60}")
    print(f"RUNNING BACKTEST: {num_weeks} weeks, Top {top_n} picks per week")
    print(f"{'='*60}\n")
    
    screening_dates = get_screening_dates(df, num_weeks)
    print(f"Testing {len(screening_dates)} screening weeks...")
    
    all_trades = []
    weekly_returns = []
    
    for i, screen_date in enumerate(screening_dates):
        # Run screener
        candidates = run_screener_for_date(df, screen_date, top_n=top_n)
        
        if candidates.empty:
            continue
        
        week_trades = []
        
        for _, row in candidates.iterrows():
            # Simulate trade
            result = simulate_trade(
                df, row['symbol'], screen_date,
                row['entry_price'], row['stop_loss'], row['target_price']
            )
            
            trade = {
                'screening_date': screen_date,
                'symbol': row['symbol'],
                'sector': row['sector'],
                'score': row['score'],
                'entry_price': row['entry_price'],
                'stop_loss': row['stop_loss'],
                'target_price': row['target_price'],
                'risk_pct': row['risk_pct'],
                'expected_reward_pct': row['reward_pct'],
                'actual_entry': result.get('actual_entry', row['entry_price']),
                'exit_price': result['exit_price'],
                'exit_reason': result['exit_reason'],
                'return_pct': result['return_pct'],
                'bars_held': result['bars_held']
            }
            
            all_trades.append(trade)
            week_trades.append(trade)
        
        # Calculate weekly return (average of trades)
        if week_trades:
            avg_return = np.mean([t['return_pct'] for t in week_trades])
            weekly_returns.append({
                'date': screen_date,
                'num_trades': len(week_trades),
                'avg_return': avg_return,
                'best': max([t['return_pct'] for t in week_trades]),
                'worst': min([t['return_pct'] for t in week_trades])
            })
        
        # Progress
        if (i + 1) % 25 == 0:
            print(f"  Processed {i + 1}/{len(screening_dates)} weeks...")
    
    # Calculate statistics
    stats = calculate_statistics(all_trades, weekly_returns)
    
    return all_trades, stats


def calculate_statistics(trades: List[Dict], weekly_returns: List[Dict]) -> Dict:
    """Calculate comprehensive backtest statistics."""
    if not trades:
        return {'error': 'No trades executed'}
    
    returns = [t['return_pct'] for t in trades]
    winning = [r for r in returns if r > 0]
    losing = [r for r in returns if r <= 0]
    
    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        reason = t['exit_reason']
        if reason not in exit_reasons:
            exit_reasons[reason] = {'count': 0, 'avg_return': []}
        exit_reasons[reason]['count'] += 1
        exit_reasons[reason]['avg_return'].append(t['return_pct'])
    
    for reason in exit_reasons:
        exit_reasons[reason]['avg_return'] = np.mean(exit_reasons[reason]['avg_return'])
    
    # Weekly stats
    weekly_df = pd.DataFrame(weekly_returns)
    
    stats = {
        'total_trades': len(trades),
        'total_weeks': len(weekly_returns),
        
        # Win/Loss
        'winning_trades': len(winning),
        'losing_trades': len(losing),
        'win_rate': (len(winning) / len(trades)) * 100,
        
        # Returns
        'avg_return_per_trade': np.mean(returns),
        'median_return': np.median(returns),
        'std_return': np.std(returns),
        'best_trade': max(returns),
        'worst_trade': min(returns),
        
        # Weekly
        'avg_weekly_return': weekly_df['avg_return'].mean() if not weekly_df.empty else 0,
        'weeks_profitable': (weekly_df['avg_return'] > 0).sum() if not weekly_df.empty else 0,
        'weeks_losing': (weekly_df['avg_return'] <= 0).sum() if not weekly_df.empty else 0,
        
        # Target achievement
        'target_hit_rate': (len([t for t in trades if t['exit_reason'] == 'target']) / len(trades)) * 100,
        'stop_hit_rate': (len([t for t in trades if t['exit_reason'] == 'stop_loss']) / len(trades)) * 100,
        
        # Risk metrics
        'profit_factor': abs(sum(winning)) / abs(sum(losing)) if losing else float('inf'),
        'avg_bars_held': np.mean([t['bars_held'] for t in trades]),
        
        # Exit breakdown
        'exit_breakdown': exit_reasons
    }
    
    # Calculate expectancy
    stats['expectancy'] = (
        (stats['win_rate'] / 100) * np.mean(winning) if winning else 0
    ) - (
        ((100 - stats['win_rate']) / 100) * abs(np.mean(losing)) if losing else 0
    )
    
    return stats


def print_results(trades: List[Dict], stats: Dict):
    """Print formatted backtest results."""
    print("\n" + "="*60)
    print("BACKTEST RESULTS SUMMARY")
    print("="*60)
    
    print(f"\n📊 TRADE STATISTICS:")
    print(f"   Total Trades:       {stats['total_trades']}")
    print(f"   Total Weeks:        {stats['total_weeks']}")
    print(f"   Winning Trades:     {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
    print(f"   Losing Trades:      {stats['losing_trades']}")
    
    print(f"\n💰 RETURN METRICS:")
    print(f"   Avg Return/Trade:   {stats['avg_return_per_trade']:+.2f}%")
    print(f"   Median Return:      {stats['median_return']:+.2f}%")
    print(f"   Best Trade:         {stats['best_trade']:+.2f}%")
    print(f"   Worst Trade:        {stats['worst_trade']:+.2f}%")
    print(f"   Return Std Dev:     {stats['std_return']:.2f}%")
    
    print(f"\n📅 WEEKLY PERFORMANCE:")
    print(f"   Avg Weekly Return:  {stats['avg_weekly_return']:+.2f}%")
    print(f"   Profitable Weeks:   {stats['weeks_profitable']}")
    print(f"   Losing Weeks:       {stats['weeks_losing']}")
    week_win_rate = stats['weeks_profitable'] / stats['total_weeks'] * 100 if stats['total_weeks'] > 0 else 0
    print(f"   Weekly Win Rate:    {week_win_rate:.1f}%")
    
    print(f"\n🎯 EXIT ANALYSIS:")
    print(f"   Target Hit Rate:    {stats['target_hit_rate']:.1f}%")
    print(f"   Stop Hit Rate:      {stats['stop_hit_rate']:.1f}%")
    print(f"   Avg Holding Period: {stats['avg_bars_held']:.1f} days")
    
    print(f"\n⚖️ RISK METRICS:")
    print(f"   Profit Factor:      {stats['profit_factor']:.2f}")
    print(f"   Expectancy:         {stats['expectancy']:+.2f}%")
    
    print(f"\n📈 EXIT BREAKDOWN:")
    for reason, data in stats['exit_breakdown'].items():
        print(f"   {reason:15} Count: {data['count']:4}  Avg Return: {data['avg_return']:+.2f}%")
    
    # Top performers by sector
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        print(f"\n🏭 SECTOR PERFORMANCE:")
        sector_stats = trades_df.groupby('sector').agg({
            'return_pct': ['mean', 'count'],
            'exit_reason': lambda x: (x == 'target').sum()
        }).round(2)
        sector_stats.columns = ['Avg_Return', 'Trades', 'Target_Hits']
        sector_stats = sector_stats.sort_values('Avg_Return', ascending=False).head(10)
        for sector, row in sector_stats.iterrows():
            print(f"   {sector:20} Avg: {row['Avg_Return']:+.2f}%  Trades: {int(row['Trades'])}  Targets: {int(row['Target_Hits'])}")
    
    # Strategy assessment
    print(f"\n{'='*60}")
    print("STRATEGY ASSESSMENT")
    print("="*60)
    
    if stats['avg_weekly_return'] >= 5:
        print("✅ EXCELLENT: Strategy achieves 5-7% weekly target!")
    elif stats['avg_weekly_return'] >= 2:
        print("✅ GOOD: Strategy achieves 2-5% weekly returns.")
    elif stats['avg_weekly_return'] >= 0:
        print("⚠️ MARGINAL: Strategy is profitable but below target.")
    else:
        print("❌ NEEDS IMPROVEMENT: Strategy is not profitable.")
    
    if stats['win_rate'] >= 55:
        print("✅ Win rate is solid (>55%)")
    else:
        print("⚠️ Win rate needs improvement")
    
    if stats['profit_factor'] >= 1.5:
        print("✅ Profit factor is healthy (>1.5)")
    else:
        print("⚠️ Profit factor needs improvement")


def main():
    """Main backtest execution."""
    print("\n" + "="*60)
    print("NSE WEEKLY SWING TRADING STRATEGY BACKTEST")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data
    df = load_all_data()
    
    # Run main backtest with top 2 picks
    trades, stats = run_backtest(df, num_weeks=150, top_n=2)
    
    # Print results
    print_results(trades, stats)
    
    # Save trades to CSV for analysis
    trades_df = pd.DataFrame(trades)
    trades_df.to_csv('backtest_trades.csv', index=False)
    print(f"\n📁 Trade log saved to: backtest_trades.csv")
    
    # Test alternative configurations
    print("\n\n" + "="*60)
    print("TESTING ALTERNATIVE CONFIGURATIONS")
    print("="*60)
    
    configs = [
        {'top_n': 3, 'weeks': 100},
        {'top_n': 5, 'weeks': 100},
    ]
    
    for cfg in configs:
        print(f"\n--- Top {cfg['top_n']} picks, {cfg['weeks']} weeks ---")
        _, alt_stats = run_backtest(df, num_weeks=cfg['weeks'], top_n=cfg['top_n'])
        print(f"   Win Rate: {alt_stats['win_rate']:.1f}%")
        print(f"   Avg Return/Trade: {alt_stats['avg_return_per_trade']:+.2f}%")
        print(f"   Avg Weekly Return: {alt_stats['avg_weekly_return']:+.2f}%")
        print(f"   Target Hit Rate: {alt_stats['target_hit_rate']:.1f}%")
    
    print(f"\n\nBacktest completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
