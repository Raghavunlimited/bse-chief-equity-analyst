#!/usr/bin/env python3
import sqlite3
from app.config import config

conn = sqlite3.connect(config.db_path)

# Check how many stocks have data for the latest date
latest = conn.execute('SELECT MAX(trade_date) FROM eod').fetchone()[0]
print(f'Latest date in DB: {latest}')

count = conn.execute('SELECT COUNT(DISTINCT symbol) FROM eod WHERE trade_date = ?', (latest,)).fetchone()[0]
print(f'Stocks with data on {latest}: {count}')

# Show some samples from latest date
samples = conn.execute('''
    SELECT symbol, close 
    FROM eod 
    WHERE trade_date = ? 
    ORDER BY turnover DESC 
    LIMIT 10
''', (latest,)).fetchall()
print(f'\nTop 10 stocks by turnover on {latest}:')
for row in samples:
    print(f'  {row[0]}: Rs.{row[1]}')

# Check what dates exist
dates = conn.execute('SELECT DISTINCT trade_date FROM eod ORDER BY trade_date DESC LIMIT 10').fetchall()
print(f'\nLast 10 trading dates:')
for d in dates:
    print(f'  {d[0]}')

# Check the weekly picks stocks
print('\n--- Weekly picks stocks data check ---')
weekly_stocks = ['RKFORGE', 'IRFC']  # Default elite stocks
for sym in weekly_stocks:
    latest_for_sym = conn.execute('''
        SELECT trade_date, close 
        FROM eod 
        WHERE symbol = ? 
        ORDER BY trade_date DESC 
        LIMIT 1
    ''', (sym,)).fetchone()
    if latest_for_sym:
        print(f'{sym}: Latest data = {latest_for_sym[0]}, Price = Rs.{latest_for_sym[1]}')
    else:
        print(f'{sym}: No data found')

conn.close()
