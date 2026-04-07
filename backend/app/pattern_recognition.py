"""
Candlestick Pattern Recognition Module

Detects high-probability bullish patterns for swing trading:
- Bullish Engulfing
- Hammer / Inverted Hammer
- Morning Star
- Three White Soldiers
- Bullish Harami
- Piercing Line
- Consolidation Breakout
- Cup and Handle (simplified)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def detect_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """
    Bullish Engulfing: Current green candle completely engulfs previous red candle.
    High probability reversal pattern.
    """
    if len(df) < 2:
        return pd.Series([False] * len(df), index=df.index)

    prev_red = df['close'].shift(1) < df['open'].shift(1)
    curr_green = df['close'] > df['open']
    engulfs_body = (df['open'] <= df['close'].shift(1)) & (df['close'] >= df['open'].shift(1))

    return prev_red & curr_green & engulfs_body


def detect_hammer(df: pd.DataFrame) -> pd.Series:
    """
    Hammer: Small body at top, long lower shadow (2x body), little/no upper shadow.
    Bullish reversal at support.
    """
    body = abs(df['close'] - df['open'])
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']

    small_body = body <= (df['high'] - df['low']) * 0.3
    long_lower = lower_shadow >= body * 2
    small_upper = upper_shadow <= body * 0.5

    return small_body & long_lower & small_upper


def detect_inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """
    Inverted Hammer: Small body at bottom, long upper shadow, little lower shadow.
    Potential bullish reversal.
    """
    body = abs(df['close'] - df['open'])
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']

    small_body = body <= (df['high'] - df['low']) * 0.3
    long_upper = upper_shadow >= body * 2
    small_lower = lower_shadow <= body * 0.5

    return small_body & long_upper & small_lower


def detect_morning_star(df: pd.DataFrame) -> pd.Series:
    """
    Morning Star: 3-candle pattern - big red, small body (doji-like), big green.
    Strong reversal pattern.
    """
    if len(df) < 3:
        return pd.Series([False] * len(df), index=df.index)

    # First candle: Big red
    first_red = df['close'].shift(2) < df['open'].shift(2)
    first_big = abs(df['close'].shift(2) - df['open'].shift(2)) > (df['high'].shift(2) - df['low'].shift(2)) * 0.5

    # Second candle: Small body (star)
    second_small = abs(df['close'].shift(1) - df['open'].shift(1)) < (df['high'].shift(1) - df['low'].shift(1)) * 0.3

    # Third candle: Big green closing above midpoint of first
    third_green = df['close'] > df['open']
    third_big = abs(df['close'] - df['open']) > (df['high'] - df['low']) * 0.5
    closes_above_mid = df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2

    return first_red & first_big & second_small & third_green & third_big & closes_above_mid


def detect_bullish_harami(df: pd.DataFrame) -> pd.Series:
    """
    Bullish Harami: Small green candle contained within previous large red candle.
    Reversal pattern.
    """
    if len(df) < 2:
        return pd.Series([False] * len(df), index=df.index)

    prev_red = df['close'].shift(1) < df['open'].shift(1)
    prev_big = abs(df['close'].shift(1) - df['open'].shift(1)) > (df['high'].shift(1) - df['low'].shift(1)) * 0.5

    curr_green = df['close'] > df['open']
    curr_small = abs(df['close'] - df['open']) < abs(df['close'].shift(1) - df['open'].shift(1)) * 0.5

    contained = (df['open'] > df['close'].shift(1)) & (df['close'] < df['open'].shift(1))

    return prev_red & prev_big & curr_green & curr_small & contained


def detect_piercing_line(df: pd.DataFrame) -> pd.Series:
    """
    Piercing Line: Green candle opens below previous low, closes above midpoint of previous red.
    Strong reversal signal.
    """
    if len(df) < 2:
        return pd.Series([False] * len(df), index=df.index)

    prev_red = df['close'].shift(1) < df['open'].shift(1)
    curr_green = df['close'] > df['open']

    opens_below = df['open'] < df['low'].shift(1)
    closes_above_mid = df['close'] > (df['open'].shift(1) + df['close'].shift(1)) / 2
    closes_below_open = df['close'] < df['open'].shift(1)

    return prev_red & curr_green & opens_below & closes_above_mid & closes_below_open


def detect_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """
    Three White Soldiers: Three consecutive green candles with higher closes.
    Strong bullish continuation.
    """
    if len(df) < 3:
        return pd.Series([False] * len(df), index=df.index)

    green1 = df['close'].shift(2) > df['open'].shift(2)
    green2 = df['close'].shift(1) > df['open'].shift(1)
    green3 = df['close'] > df['open']

    higher_closes = (df['close'] > df['close'].shift(1)) & (df['close'].shift(1) > df['close'].shift(2))
    higher_opens = (df['open'] > df['open'].shift(1)) & (df['open'].shift(1) > df['open'].shift(2))

    return green1 & green2 & green3 & higher_closes & higher_opens


def detect_consolidation_breakout(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """
    Consolidation Breakout: Price breaks out of a tight range on volume.
    """
    if len(df) < lookback:
        return pd.Series([False] * len(df), index=df.index)

    # Calculate range over lookback period
    rolling_high = df['high'].rolling(lookback).max()
    rolling_low = df['low'].rolling(lookback).min()
    range_pct = (rolling_high - rolling_low) / rolling_low * 100

    # Tight consolidation (range < 10%)
    tight_range = range_pct < 10

    # Breakout above range high
    breakout = df['close'] > rolling_high.shift(1)

    # Volume confirmation
    vol_ma = df['volume'].rolling(20).mean()
    high_volume = df['volume'] > vol_ma * 1.5

    return tight_range.shift(1) & breakout & high_volume


def detect_higher_highs_higher_lows(df: pd.DataFrame, periods: int = 5) -> pd.Series:
    """
    Higher Highs and Higher Lows: Classic uptrend structure.
    """
    if len(df) < periods * 2:
        return pd.Series([False] * len(df), index=df.index)

    higher_highs = df['high'] > df['high'].shift(periods)
    higher_lows = df['low'] > df['low'].shift(periods)

    return higher_highs & higher_lows


def detect_all_patterns(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    Detect all bullish patterns and return a dictionary.
    """
    patterns = {
        'bullish_engulfing': detect_bullish_engulfing(df),
        'hammer': detect_hammer(df),
        'inverted_hammer': detect_inverted_hammer(df),
        'morning_star': detect_morning_star(df),
        'bullish_harami': detect_bullish_harami(df),
        'piercing_line': detect_piercing_line(df),
        'three_white_soldiers': detect_three_white_soldiers(df),
        'consolidation_breakout': detect_consolidation_breakout(df),
        'uptrend_structure': detect_higher_highs_higher_lows(df),
    }
    return patterns


def calculate_pattern_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate pattern-based score for each row.
    Returns df with pattern columns and pattern_score.
    """
    df = df.copy()

    patterns = detect_all_patterns(df)

    # Pattern weights (higher weight = more reliable pattern)
    weights = {
        'bullish_engulfing': 3,
        'hammer': 2,
        'inverted_hammer': 1,
        'morning_star': 4,  # Very reliable
        'bullish_harami': 2,
        'piercing_line': 3,
        'three_white_soldiers': 4,  # Very reliable
        'consolidation_breakout': 5,  # Most reliable for swing trading
        'uptrend_structure': 2,
    }

    # Add pattern columns
    df['pattern_score'] = 0
    df['patterns_detected'] = ''

    for pattern_name, pattern_series in patterns.items():
        df[f'pattern_{pattern_name}'] = pattern_series
        df['pattern_score'] += pattern_series.astype(int) * weights.get(pattern_name, 1)

        # Build pattern string
        df.loc[pattern_series, 'patterns_detected'] += pattern_name + ', '

    # Clean up pattern string
    df['patterns_detected'] = df['patterns_detected'].str.rstrip(', ')

    return df


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    Calculate Supertrend indicator.
    Returns df with supertrend and supertrend_direction columns.
    """
    df = df.copy()

    # Calculate ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift(1))
    low_close = abs(df['low'] - df['close'].shift(1))

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # Calculate basic bands
    hl2 = (df['high'] + df['low']) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    # Initialize supertrend
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = -1

    for i in range(1, len(df)):
        if df['close'].iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1  # Bullish
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1  # Bearish

        # Adjust bands based on previous
        if direction.iloc[i] == 1 and lower_band.iloc[i] < supertrend.iloc[i-1]:
            supertrend.iloc[i] = supertrend.iloc[i-1]
        elif direction.iloc[i] == -1 and upper_band.iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = supertrend.iloc[i-1]

    df['supertrend'] = supertrend
    df['supertrend_direction'] = direction

    return df


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculate ADX (Average Directional Index) for trend strength.
    ADX > 25 = strong trend, ADX > 40 = very strong trend.
    """
    df = df.copy()

    # Calculate +DM and -DM
    df['high_diff'] = df['high'] - df['high'].shift(1)
    df['low_diff'] = df['low'].shift(1) - df['low']

    df['+dm'] = np.where((df['high_diff'] > df['low_diff']) & (df['high_diff'] > 0), df['high_diff'], 0)
    df['-dm'] = np.where((df['low_diff'] > df['high_diff']) & (df['low_diff'] > 0), df['low_diff'], 0)

    # Calculate TR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift(1))
    low_close = abs(df['low'] - df['close'].shift(1))
    df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # Smoothed values
    df['atr'] = df['tr'].rolling(period).mean()
    df['+di'] = 100 * (df['+dm'].rolling(period).mean() / df['atr'])
    df['-di'] = 100 * (df['-dm'].rolling(period).mean() / df['atr'])

    # DX and ADX
    df['dx'] = 100 * abs(df['+di'] - df['-di']) / (df['+di'] + df['-di'])
    df['adx'] = df['dx'].rolling(period).mean()

    # Clean up temp columns
    df = df.drop(columns=['high_diff', 'low_diff', '+dm', '-dm', 'tr', 'dx'], errors='ignore')

    return df


def calculate_trend_strength(df: pd.DataFrame) -> pd.DataFrame:
    """
    Comprehensive trend strength calculation.
    """
    df = df.copy()

    # Moving averages alignment
    if 'sma_20' not in df.columns:
        df['sma_20'] = df['close'].rolling(20).mean()
    if 'sma_50' not in df.columns:
        df['sma_50'] = df['close'].rolling(50).mean()

    df['sma_10'] = df['close'].rolling(10).mean()
    df['ema_9'] = df['close'].ewm(span=9).mean()
    df['ema_21'] = df['close'].ewm(span=21).mean()

    # MA alignment score
    df['ma_aligned'] = (
        (df['close'] > df['sma_10']).astype(int) +
        (df['sma_10'] > df['sma_20']).astype(int) +
        (df['sma_20'] > df['sma_50']).astype(int) +
        (df['ema_9'] > df['ema_21']).astype(int)
    )

    # Supertrend
    df = calculate_supertrend(df)

    # ADX
    df = calculate_adx(df)

    # Trend strength score (0-10)
    df['trend_strength'] = 0

    # MA alignment (max 4 points)
    df['trend_strength'] += df['ma_aligned']

    # Supertrend bullish (2 points)
    df['trend_strength'] += (df['supertrend_direction'] == 1).astype(int) * 2

    # Strong ADX (2 points if > 25, 4 points if > 40)
    df['trend_strength'] += np.where(df['adx'] > 40, 4, np.where(df['adx'] > 25, 2, 0))

    return df


def get_pattern_summary(row: pd.Series) -> str:
    """
    Get a human-readable pattern summary for a stock.
    """
    patterns = []

    if row.get('pattern_bullish_engulfing', False):
        patterns.append("Bullish Engulfing")
    if row.get('pattern_hammer', False):
        patterns.append("Hammer")
    if row.get('pattern_morning_star', False):
        patterns.append("Morning Star")
    if row.get('pattern_three_white_soldiers', False):
        patterns.append("3 White Soldiers")
    if row.get('pattern_consolidation_breakout', False):
        patterns.append("Breakout")
    if row.get('pattern_uptrend_structure', False):
        patterns.append("HH-HL")

    if not patterns:
        return "No clear pattern"

    return " + ".join(patterns)
