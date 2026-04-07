#!/usr/bin/env python3
"""
Create sample data for testing the screener
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from app.store import Database
from app.config import config
from app.features import compute_indicators_for_all_symbols, extract_indicator_columns

# Sample NSE stocks
symbols = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR',
    'ICICIBANK', 'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK',
    'LT', 'ASIANPAINT', 'AXISBANK', 'MARUTI', 'TITAN',
    'BAJFINANCE', 'WIPRO', 'ULTRACEMCO', 'NESTLEIND', 'SUNPHARMA',
    'TECHM', 'M&M', 'HCLTECH', 'POWERGRID', 'NTPC',
    'ONGC', 'TATASTEEL', 'ADANIENT', 'ADANIPORTS', 'JSWSTEEL'
]

# Generate 100 days of sample data (will give us ~70 trading days)
end_date = datetime.now()
start_date = end_date - timedelta(days=100)

all_data = []

for symbol in symbols:
    # Random starting price
    np.random.seed(hash(symbol) % 2**32)
    base_price = np.random.uniform(100, 3000)

    # Create trending behavior for some stocks
    trend = np.random.choice([0.002, -0.001, 0])  # uptrend, downtrend, or sideways

    # Generate realistic OHLCV data
    for i in range(100):
        date = start_date + timedelta(days=i)

        # Skip weekends
        if date.weekday() >= 5:
            continue

        # Add trend + random walk
        change = trend + np.random.randn() * 0.015
        base_price = base_price * (1 + change)

        # OHLC
        close = base_price
        open_price = close * (1 + np.random.uniform(-0.01, 0.01))
        high = max(open_price, close) * (1 + np.random.uniform(0, 0.02))
        low = min(open_price, close) * (1 - np.random.uniform(0, 0.02))

        # Volume and turnover (much higher for liquid stocks)
        # Make sure turnover > ₹10 Cr for most stocks
        volume = np.random.uniform(1000000, 50000000)  # 10 lakh to 5 crore shares
        turnover = volume * close

        all_data.append({
            'symbol': symbol,
            'trade_date': date.strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': int(volume),
            'turnover': round(turnover, 2),
            'prev_close': round(close * 0.99, 2)
        })

# Create DataFrame
df = pd.DataFrame(all_data)

print(f"Generated {len(df)} records for {len(symbols)} symbols")

# Initialize database
db = Database(config.db_path)

# Store EOD data
db.upsert_eod_data(df)
print(f"Stored {len(df)} EOD records in database")

# Compute indicators
with_indicators = compute_indicators_for_all_symbols(df)
indicators_df = extract_indicator_columns(with_indicators)
db.upsert_indicators(indicators_df)
print(f"Computed and stored indicators for {len(symbols)} symbols")

print("\n✅ Sample data created successfully!")
print(f"Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
print(f"Total symbols: {len(symbols)}")
print("\nYou can now run the screener!")
