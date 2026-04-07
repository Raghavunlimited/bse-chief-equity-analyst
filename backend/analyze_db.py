#!/usr/bin/env python3
"""Database performance analysis script"""
import sqlite3
import time
from app.config import config

conn = sqlite3.connect(config.db_path)
cur = conn.cursor()

print('=== Database Analysis ===')
cur.execute('SELECT COUNT(*) FROM eod')
print(f'EOD rows: {cur.fetchone()[0]:,}')

cur.execute('SELECT COUNT(*) FROM indicators')
print(f'Indicator rows: {cur.fetchone()[0]:,}')

# Check indexes
cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
indexes = cur.fetchall()
print(f'Indexes: {[i[0] for i in indexes]}')

# Latest date
cur.execute('SELECT MAX(trade_date) FROM eod')
print(f'Latest data: {cur.fetchone()[0]}')

# Test query performance
start = time.time()
cur.execute('''SELECT e.symbol, e.close, i.rsi_14 
               FROM eod e 
               JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date 
               WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)''')
rows = cur.fetchall()
print(f'Join query time: {time.time()-start:.3f}s for {len(rows)} rows')

conn.close()
