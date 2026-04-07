"""
Ultimate Swing Trading Screener

Combines multiple factors for high win-rate stock selection:
1. Pattern Recognition (candlestick patterns)
2. Trend Strength (ADX, Supertrend, MA alignment)
3. Sector Momentum (only trade top sectors)
4. Volume Confirmation
5. Support/Resistance proximity
6. Relative Strength vs NIFTY
7. Risk/Reward optimization
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime
import json

from app.pattern_recognition import (
    calculate_pattern_score,
    calculate_trend_strength,
    get_pattern_summary
)
from app.sector_analysis import calculate_sector_metrics


def calculate_volume_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate volume-based signals.
    """
    df = df.copy()

    if 'vol_ma_20' not in df.columns:
        df['vol_ma_20'] = df['volume'].rolling(20).mean()

    df['vol_ratio'] = df['volume'] / df['vol_ma_20']

    # Volume trend (increasing over last 5 days)
    df['vol_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()

    # Accumulation (green candles with high volume)
    df['is_green'] = df['close'] > df['open']
    df['accumulation'] = (df['is_green'] & (df['vol_ratio'] > 1.2)).rolling(5).sum()

    # Volume score (0-4 points)
    df['volume_score'] = 0
    df['volume_score'] += (df['vol_ratio'] > 1).astype(int)
    df['volume_score'] += (df['vol_ratio'] > 1.5).astype(int)
    df['volume_score'] += (df['vol_trend'] > 1).astype(int)
    df['volume_score'] += (df['accumulation'] >= 2).astype(int)

    return df


def calculate_support_resistance_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate how close price is to support levels (safer entry).
    """
    df = df.copy()

    # Calculate support levels
    df['support_20'] = df['low'].rolling(20).min()
    df['support_50'] = df['low'].rolling(50).min()

    df['resistance_20'] = df['high'].rolling(20).max()
    df['resistance_50'] = df['high'].rolling(50).max()

    # Distance from support
    df['dist_from_support'] = (df['close'] - df['support_20']) / df['support_20'] * 100

    # Distance from resistance (upside potential)
    df['dist_to_resistance'] = (df['resistance_50'] - df['close']) / df['close'] * 100

    # Entry quality score (0-4 points)
    df['entry_score'] = 0

    # Close to support (within 5%)
    df['entry_score'] += (df['dist_from_support'] < 5).astype(int) * 2

    # Good upside potential (> 10%)
    df['entry_score'] += (df['dist_to_resistance'] > 10).astype(int)
    df['entry_score'] += (df['dist_to_resistance'] > 15).astype(int)

    return df


def calculate_momentum_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate momentum indicators and score.
    """
    df = df.copy()

    # RSI
    if 'rsi_14' not in df.columns:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))

    # ROC (Rate of Change)
    df['roc_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5) * 100
    df['roc_10'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10) * 100
    df['roc_20'] = (df['close'] - df['close'].shift(20)) / df['close'].shift(20) * 100

    # MACD
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Momentum score (0-6 points)
    df['momentum_score'] = 0

    # RSI in bullish zone (40-70)
    df['momentum_score'] += ((df['rsi_14'] > 40) & (df['rsi_14'] < 70)).astype(int)
    df['momentum_score'] += ((df['rsi_14'] > 50) & (df['rsi_14'] < 65)).astype(int)  # Sweet spot

    # Positive ROC
    df['momentum_score'] += (df['roc_5'] > 0).astype(int)
    df['momentum_score'] += (df['roc_10'] > 0).astype(int)

    # MACD bullish
    df['momentum_score'] += (df['macd'] > df['macd_signal']).astype(int)
    df['momentum_score'] += (df['macd_hist'] > df['macd_hist'].shift(1)).astype(int)  # Increasing histogram

    return df


def calculate_ultimate_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the ultimate composite score combining all factors.
    """
    df = df.copy()

    # Calculate all component scores
    df = calculate_pattern_score(df)
    df = calculate_trend_strength(df)
    df = calculate_volume_signals(df)
    df = calculate_support_resistance_score(df)
    df = calculate_momentum_score(df)

    # Ultimate Score Calculation (max ~50 points)
    df['ultimate_score'] = 0

    # 1. Pattern Score (max ~15 points)
    df['ultimate_score'] += df['pattern_score'].clip(upper=15)

    # 2. Trend Strength (max 10 points)
    df['ultimate_score'] += df['trend_strength']

    # 3. Volume Score (max 4 points)
    df['ultimate_score'] += df['volume_score']

    # 4. Entry Quality (max 4 points)
    df['ultimate_score'] += df['entry_score']

    # 5. Momentum Score (max 6 points)
    df['ultimate_score'] += df['momentum_score']

    # 6. Relative Strength bonus (max 5 points)
    if 'relative_strength' in df.columns:
        df['ultimate_score'] += np.where(df['relative_strength'] > 1.1, 5,
                                  np.where(df['relative_strength'] > 1.05, 3,
                                  np.where(df['relative_strength'] > 1, 1, 0)))

    # Normalize to 0-100 scale
    df['ultimate_score_pct'] = (df['ultimate_score'] / 45 * 100).clip(upper=100)

    # Strength classification
    df['signal_strength'] = pd.cut(
        df['ultimate_score_pct'],
        bins=[0, 30, 50, 70, 85, 100],
        labels=['WEAK', 'MODERATE', 'GOOD', 'STRONG', 'EXCELLENT']
    )

    return df


def get_sector_rankings(df: pd.DataFrame) -> Dict:
    """
    Get sector rankings for filtering.
    """
    sector_metrics = calculate_sector_metrics(df)

    top_sectors = []
    for sector in sector_metrics:
        if sector['phase'] in ['LEADING', 'IMPROVING']:
            top_sectors.append(sector['sector'])

    return {
        'top_sectors': top_sectors[:5],
        'metrics': sector_metrics
    }


def run_ultimate_screener(
        df: pd.DataFrame,
        top_n: int = 20,
        capital_per_trade: float = 100000,
        min_score: float = 50,  # Minimum ultimate score percentage
        require_pattern: bool = True,
        require_trend: bool = True,
        sector_filter: bool = True,
        max_risk_pct: float = 5.0
) -> Dict:
    """
    Run the ultimate screener with all filters.

    Parameters:
    - df: DataFrame with OHLCV data
    - top_n: Number of top stocks to return
    - capital_per_trade: Capital per position
    - min_score: Minimum ultimate score percentage (0-100)
    - require_pattern: Require at least one bullish pattern
    - require_trend: Require positive trend strength
    - sector_filter: Only trade stocks in top sectors
    - max_risk_pct: Maximum risk per trade

    Returns:
    - Dictionary with candidates and analysis
    """

    if df.empty:
        return {
            'status': 'error',
            'message': 'No data provided',
            'candidates': [],
            'stats': {}
        }

    results = {
        'screening_date': datetime.now().strftime('%Y-%m-%d'),
        'filters_applied': [],
        'stats': {
            'total_stocks': len(df),
            'passed_filters': 0,
            'avg_score': 0
        },
        'sector_analysis': {},
        'candidates': [],
        'rejected': []
    }

    # Get latest data per symbol
    df = df.sort_values('trade_date').groupby('symbol').last().reset_index()
    results['stats']['total_stocks'] = len(df)

    # Calculate ultimate score
    df = calculate_ultimate_score(df)

    # Get sector rankings if needed
    if sector_filter and 'sector' in df.columns:
        sector_info = get_sector_rankings(df)
        results['sector_analysis'] = sector_info
        top_sectors = sector_info['top_sectors']
        results['filters_applied'].append(f'Sector Filter (Top: {", ".join(top_sectors[:3])})')
    else:
        top_sectors = None

    # Apply filters
    mask = pd.Series([True] * len(df), index=df.index)

    # 1. Minimum score filter
    mask &= df['ultimate_score_pct'].fillna(0) >= min_score
    results['filters_applied'].append(f'Min Score: {min_score}%')

    # 2. Pattern filter
    if require_pattern:
        mask &= df['pattern_score'].fillna(0) > 0
        results['filters_applied'].append('Pattern Required')

    # 3. Trend filter
    if require_trend:
        mask &= df['trend_strength'].fillna(0) >= 4  # At least moderate trend
        results['filters_applied'].append('Trend Required (>=4)')

    # 4. Sector filter
    if sector_filter and top_sectors:
        sector_list = list(top_sectors) + ['Unknown']
        mask &= df['sector'].isin(sector_list)

    # 5. Volume filter (minimum liquidity)
    if 'volume' in df.columns:
        min_volume = df['volume'].quantile(0.2)  # Top 80% by volume
        mask &= df['volume'] >= min_volume
        results['filters_applied'].append('Volume Liquidity Filter')

    # 6. RSI not overbought
    if 'rsi_14' in df.columns:
        mask &= df['rsi_14'] < 75
        results['filters_applied'].append('RSI < 75')

    # Apply filters
    filtered = df[mask].copy()
    rejected = df[~mask].copy()

    results['stats']['passed_filters'] = len(filtered)

    # Calculate entry, stop, target for candidates
    if len(filtered) > 0:
        # Entry at current close
        filtered['entry_price'] = filtered['close']

        # Stop loss based on ATR or support
        if 'atr_14' in filtered.columns:
            filtered['stop_loss'] = filtered['close'] - (filtered['atr_14'] * 1.5)
        else:
            filtered['stop_loss'] = filtered['close'] * 0.97  # 3% default

        # Ensure stop loss is not too far (max risk_pct)
        max_sl = filtered['close'] * (1 - max_risk_pct / 100)
        filtered['stop_loss'] = np.maximum(filtered['stop_loss'], max_sl)

        # Target based on R:R ratio (aim for 2:1 or better)
        risk_per_share = filtered['entry_price'] - filtered['stop_loss']
        filtered['target_price'] = filtered['entry_price'] + (risk_per_share * 2.5)

        # Risk reward
        filtered['risk_pct'] = (filtered['entry_price'] - filtered['stop_loss']) / filtered['entry_price'] * 100
        filtered['reward_pct'] = (filtered['target_price'] - filtered['entry_price']) / filtered['entry_price'] * 100
        filtered['risk_reward'] = filtered['reward_pct'] / filtered['risk_pct']

        # Position sizing (risk-based)
        risk_amount = capital_per_trade * 0.02  # 2% risk per trade
        filtered['position_size'] = (risk_amount / risk_per_share).astype(int)
        filtered['position_size'] = filtered['position_size'].clip(lower=1)
        filtered['position_value'] = filtered['position_size'] * filtered['entry_price']

        # Sort by ultimate score
        filtered = filtered.sort_values('ultimate_score_pct', ascending=False)

        # Take top N
        top_candidates = filtered.head(top_n)

        results['stats']['avg_score'] = float(filtered['ultimate_score_pct'].mean())

        # Build candidate list
        for _, row in top_candidates.iterrows():
            pattern_summary = get_pattern_summary(row)

            candidate = {
                'symbol': str(row['symbol']),
                'sector': str(row.get('sector', 'Unknown')),
                'score': round(float(row['ultimate_score_pct']), 1),
                'signal_strength': str(row['signal_strength']) if pd.notna(row.get('signal_strength')) else 'MODERATE',
                'close_price': round(float(row['close']), 2),
                'entry_price': round(float(row['entry_price']), 2),
                'stop_loss': round(float(row['stop_loss']), 2),
                'target_price': round(float(row['target_price']), 2),
                'risk_pct': round(float(row['risk_pct']), 2),
                'reward_pct': round(float(row['reward_pct']), 2),
                'risk_reward': round(float(row['risk_reward']), 2),
                'position_size': int(row['position_size']),
                'position_value': round(float(row['position_value']), 2),
                'metadata': {
                    'pattern_score': int(row.get('pattern_score', 0)),
                    'patterns': str(pattern_summary),
                    'trend_strength': int(row.get('trend_strength', 0)),
                    'volume_score': int(row.get('volume_score', 0)),
                    'momentum_score': int(row.get('momentum_score', 0)),
                    'entry_score': int(row.get('entry_score', 0)),
                    'rsi_14': round(float(row.get('rsi_14', 50)), 1) if pd.notna(row.get('rsi_14')) else 50.0,
                    'adx': round(float(row.get('adx', 0)), 1) if pd.notna(row.get('adx')) else 0.0,
                    'supertrend': 'BULLISH' if row.get('supertrend_direction', 0) == 1 else 'BEARISH',
                    'vol_ratio': round(float(row.get('vol_ratio', 1)), 2) if pd.notna(row.get('vol_ratio')) else 1.0,
                    'relative_strength': round(float(row.get('relative_strength', 1)), 3) if pd.notna(row.get('relative_strength')) else 1.0,
                    'dist_from_support': round(float(row.get('dist_from_support', 0)), 1) if pd.notna(row.get('dist_from_support')) else 0.0,
                }
            }
            results['candidates'].append(candidate)

    # Add rejection reasons for analysis
    if len(rejected) > 0:
        for _, row in rejected.head(10).iterrows():
            reason = []
            score_val = float(row.get('ultimate_score_pct', 0)) if pd.notna(row.get('ultimate_score_pct')) else 0.0
            if score_val < min_score:
                reason.append(f"Low score ({score_val:.1f}%)")
            if require_pattern and int(row.get('pattern_score', 0)) == 0:
                reason.append("No pattern")
            trend_val = int(row.get('trend_strength', 0)) if pd.notna(row.get('trend_strength')) else 0
            if require_trend and trend_val < 4:
                reason.append(f"Weak trend ({trend_val})")
            sect = str(row.get('sector', 'Unknown'))
            if top_sectors and sect not in top_sectors:
                reason.append(f"Sector not hot ({sect})")

            results['rejected'].append({
                'symbol': str(row['symbol']),
                'score': round(score_val, 1),
                'reasons': reason
            })

    results['status'] = 'success'
    return results


def get_screener_summary() -> Dict:
    """
    Get explanation of the screener methodology.
    """
    return {
        "name": "Ultimate Swing Screener",
        "version": "2.0",
        "methodology": {
            "pattern_recognition": {
                "description": "Detects bullish candlestick patterns",
                "patterns": [
                    "Bullish Engulfing (3 pts)",
                    "Morning Star (4 pts)",
                    "Three White Soldiers (4 pts)",
                    "Consolidation Breakout (5 pts)",
                    "Hammer (2 pts)",
                    "Piercing Line (3 pts)"
                ],
                "weight": "15 points max"
            },
            "trend_strength": {
                "description": "Multi-indicator trend analysis",
                "indicators": [
                    "Moving Average Alignment (4 pts)",
                    "Supertrend Direction (2 pts)",
                    "ADX Trend Strength (4 pts)"
                ],
                "weight": "10 points max"
            },
            "volume_analysis": {
                "description": "Volume confirmation signals",
                "signals": [
                    "Above average volume",
                    "Volume trend increasing",
                    "Accumulation pattern"
                ],
                "weight": "4 points max"
            },
            "entry_quality": {
                "description": "Support/resistance proximity",
                "factors": [
                    "Close to support",
                    "Upside potential to resistance"
                ],
                "weight": "4 points max"
            },
            "momentum": {
                "description": "Momentum indicators",
                "indicators": [
                    "RSI sweet spot (40-70)",
                    "Positive Rate of Change",
                    "MACD bullish"
                ],
                "weight": "6 points max"
            },
            "relative_strength": {
                "description": "Outperformance vs NIFTY",
                "weight": "5 points max"
            }
        },
        "filters": [
            "Minimum score threshold (default 50%)",
            "Pattern required (at least one bullish pattern)",
            "Trend strength >= 4",
            "Top sectors only",
            "Minimum liquidity",
            "RSI not overbought (< 75)"
        ],
        "risk_management": {
            "stop_loss": "1.5x ATR below entry",
            "target": "2.5x risk for 2.5:1 R:R",
            "position_sizing": "2% risk per trade"
        }
    }
