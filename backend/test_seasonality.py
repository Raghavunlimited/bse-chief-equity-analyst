#!/usr/bin/env python3
"""Test seasonality statistics validation"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.sector_seasonality import calculate_sector_seasonality, validate_seasonality_stats, MONTH_NAMES, get_top_sectors_for_month
from app.store import Database
from app.config import config
import pandas as pd

# Load data from database
db = Database(config.db_path)
with db.get_connection() as conn:
    df = pd.read_sql_query('SELECT symbol, trade_date, open, high, low, close, volume FROM eod ORDER BY symbol, trade_date', conn)

if df.empty:
    print('No data in database')
    sys.exit(1)

# Add sector information
from nse_stocks import SECTOR_MAP
df['sector'] = df['symbol'].map(SECTOR_MAP).fillna('Unknown')
df = df[df['sector'] != 'Unknown']

print(f'Total records: {len(df):,}')
print(f'Unique stocks: {df["symbol"].nunique()}')
print(f'Unique sectors: {df["sector"].nunique()}')
print(f'Date range: {df["trade_date"].min()} to {df["trade_date"].max()}')
print()

# Run validation
validation = validate_seasonality_stats(df)
print('=== VALIDATION RESULTS ===')
all_passed = all(c['passed'] for c in validation['sanity_checks'])
print(f'Overall status: {"VALID" if all_passed else "NEEDS REVIEW"}')
print()
for check in validation['sanity_checks']:
    status = 'PASS' if check['passed'] else 'FAIL'
    print(f'{status}: {check["check"]}: {check["value"]}')
print()

# Test heatmap calculation
heatmap = calculate_sector_seasonality(df)
print(f'=== HEATMAP: {len(heatmap)} sectors generated ===')

# Show sample sector data
if heatmap:
    sample_sector = list(heatmap.keys())[0]
    print(f'\nSample sector: {sample_sector}')
    for month, data in list(heatmap[sample_sector].items())[:3]:
        print(f'  {month}: Avg {data["avg_return"]:+.2f}%, Win Rate {data["win_rate"]}%')

# Show top 3 sectors for February
top_sectors = get_top_sectors_for_month(df, month=2, top_n=3)
print(f'\n=== TOP SECTORS FOR FEBRUARY (month 2) ===')
if top_sectors:
    for i, s in enumerate(top_sectors, 1):
        print(f'{i}. {s["sector"]} | Avg Return: {s["avg_return"]:+.2f}% | Win Rate: {s["win_rate"]}%')
else:
    print('No sectors found (may need more data points)')

print('\n=== TEST COMPLETE ===')
