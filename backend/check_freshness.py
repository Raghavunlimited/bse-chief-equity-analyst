#!/usr/bin/env python3
import sqlite3
import sys
sys.path.insert(0, '/Users/raghav/Desktop/weekly_swing/backend')
from app.config import config

conn = sqlite3.connect(config.db_path)

# Find stocks with stale data
latest = conn.execute('SELECT MAX(trade_date) FROM eod').fetchone()[0]
print(f'Latest date in DB: {latest}')

# Count stocks by their latest data date
stale = conn.execute('''
    SELECT 
        CASE 
            WHEN latest_date = ? THEN 'Current (Feb 2026)'
            WHEN latest_date >= '2025-01-01' THEN '2025 data'
            WHEN latest_date >= '2024-01-01' THEN '2024 data'
            WHEN latest_date >= '2023-01-01' THEN '2023 data'
            ELSE 'Very old (<2023)'
        END as category,
        COUNT(*) as count
    FROM (
        SELECT symbol, MAX(trade_date) as latest_date
        FROM eod
        GROUP BY symbol
    )
    GROUP BY category
    ORDER BY count DESC
''', (latest,)).fetchall()

print('\nStock data freshness:')
for cat, count in stale:
    print(f'  {cat}: {count} stocks')

# Show some examples of popular stocks with old data  
popular = ['TATAMOTORS', 'TATAPOWER', 'ADANIENT', 'HDFC', 'ICICIBANK', 'AXISBANK', 'MARUTI', 'RELIANCE', 'TCS', 'INFY']
print('\nPopular stocks check:')
for sym in popular:
    result = conn.execute('SELECT MAX(trade_date), close FROM eod WHERE symbol = ? ORDER BY trade_date DESC LIMIT 1', (sym,)).fetchone()
    if result:
        print(f'  {sym}: {result[0]} - Rs.{result[1]}')
    else:
        print(f'  {sym}: No data')

conn.close()
