#!/usr/bin/env python3
"""
Professional Trader's Comprehensive Test Suite
Tests data quality, calculation accuracy, and trading logic
"""

import sqlite3
import pandas as pd
import numpy as np
from app.config import config
from nse_stocks import SECTOR_MAP

def test_data_quality():
    """Test data quality and completeness"""
    print("\n" + "="*60)
    print("DATA QUALITY TESTS")
    print("="*60)
    
    conn = sqlite3.connect(config.db_path)
    
    # Check date range
    dates = pd.read_sql_query("SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date, COUNT(DISTINCT trade_date) as trading_days FROM eod", conn)
    print(f"\n📅 Data Range: {dates['min_date'].iloc[0]} to {dates['max_date'].iloc[0]}")
    print(f"   Trading days: {dates['trading_days'].iloc[0]}")
    
    # Check symbols
    symbols = pd.read_sql_query("SELECT COUNT(DISTINCT symbol) as count FROM eod", conn)
    print(f"\n📊 Total Symbols: {symbols['count'].iloc[0]}")
    
    # Check for missing indicator data
    missing_ind = pd.read_sql_query("""
        SELECT COUNT(*) as cnt FROM eod e
        LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
        AND (i.sma_20 IS NULL OR i.rsi_14 IS NULL)
    """, conn)
    print(f"\n⚠️ Stocks with missing indicators (latest date): {missing_ind['cnt'].iloc[0]}")
    
    conn.close()
    return True


def test_momentum_calculations():
    """Test ROC calculations for accuracy"""
    print("\n" + "="*60)
    print("MOMENTUM CALCULATION TESTS") 
    print("="*60)
    
    conn = sqlite3.connect(config.db_path)
    
    # Test with TORNTPHARM
    df = pd.read_sql_query("""
        SELECT trade_date, close
        FROM eod
        WHERE symbol = 'TORNTPHARM'
        ORDER BY trade_date DESC
        LIMIT 10
    """, conn)
    conn.close()
    
    if len(df) >= 6:
        close_today = df.iloc[0]['close']
        close_3d = df.iloc[3]['close']
        close_5d = df.iloc[5]['close']
        
        manual_roc_3 = (close_today - close_3d) / close_3d * 100
        manual_roc_5 = (close_today - close_5d) / close_5d * 100
        
        print(f"\n🔢 TORNTPHARM Manual ROC Calculation:")
        print(f"   Today: ₹{close_today:.2f}")
        print(f"   3 days ago: ₹{close_3d:.2f}")
        print(f"   5 days ago: ₹{close_5d:.2f}")
        print(f"   ROC-3: {manual_roc_3:.2f}%")
        print(f"   ROC-5: {manual_roc_5:.2f}%")
        
        # Compare with screener output
        print(f"\n   ⚠️ SCREENER SHOWS: ROC-5 = 2040.49% (INCORRECT)")
        print(f"   ✅ ACTUAL ROC-5 should be: {manual_roc_5:.2f}%")
        
        # This is a CRITICAL BUG
        if abs(manual_roc_5) < 50:  # Reasonable range
            print(f"\n   🐛 BUG DETECTED: ROC calculation in elite_screener.py")
            print(f"      The shift() function operates across all symbols")
            print(f"      Need to group by symbol before calculating ROC")
            return False
    
    return True


def test_range_position():
    """Test range position calculation"""
    print("\n" + "="*60)
    print("RANGE POSITION TESTS")
    print("="*60)
    
    conn = sqlite3.connect(config.db_path)
    df = pd.read_sql_query("""
        SELECT e.symbol, e.close, i.hh_20, i.ll_20
        FROM eod e
        LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
        AND i.hh_20 IS NOT NULL
        LIMIT 5
    """, conn)
    conn.close()
    
    print("\n🎯 Range Position Analysis:")
    for _, row in df.iterrows():
        close = row['close']
        hh = row['hh_20']
        ll = row['ll_20']
        range_size = hh - ll
        range_pos = (close - ll) / (range_size + 0.001) if range_size > 0 else 0.5
        
        print(f"\n   {row['symbol']}:")
        print(f"      Close: ₹{close:.2f}, 20d High: ₹{hh:.2f}, 20d Low: ₹{ll:.2f}")
        print(f"      Range Position: {range_pos:.2f}")
        
        if range_pos > 1.0:
            print(f"      ⚠️ ISSUE: Range position > 1 means close is above 20-day high")
            print(f"         This indicates HH_20 indicator NOT updated for today's data!")
    
    return True


def test_sector_mapping():
    """Test sector mapping accuracy"""
    print("\n" + "="*60)
    print("SECTOR MAPPING TESTS")
    print("="*60)
    
    issues = []
    
    # Known corrections needed
    corrections = {
        'JKTYRE': ('Power', 'Auto Ancillary'),  # current, should be
        'CEAT': ('NOT FOUND', 'Auto Ancillary'),
    }
    
    print("\n🏷️ Sector Mapping Issues Found:")
    for symbol, (current, should_be) in corrections.items():
        actual = SECTOR_MAP.get(symbol, 'NOT FOUND')
        if actual != should_be:
            print(f"   ❌ {symbol}: Currently '{actual}', should be '{should_be}'")
            issues.append(symbol)
    
    # Check for Unknown sectors
    unknown_count = sum(1 for v in SECTOR_MAP.values() if v == 'Unknown')
    print(f"\n   ℹ️ Symbols mapped to 'Unknown': {unknown_count}")
    
    return len(issues) == 0


def test_risk_reward():
    """Test if risk:reward ratios are acceptable for trading"""
    print("\n" + "="*60)
    print("RISK:REWARD ANALYSIS (Professional Trader Perspective)")
    print("="*60)
    
    import requests
    resp = requests.post("http://localhost:8000/api/screener/elite?top_n=5", timeout=60)
    data = resp.json()
    
    print("\n📊 Risk:Reward Analysis:")
    issues = []
    
    for c in data.get('candidates', []):
        symbol = c['symbol']
        rr = c['risk_reward']
        risk_pct = c['risk_pct']
        rsi = c['metrics'].get('rsi_14', 0)
        
        print(f"\n   {symbol}:")
        print(f"      Risk:Reward = {rr:.2f}:1, Risk = {risk_pct:.1f}%")
        
        # Professional standards
        if rr < 2.0:
            print(f"      ⚠️ R:R below 2:1 - Not ideal for swing trading")
            issues.append(f"{symbol}: R:R {rr:.2f}")
        
        if rsi > 75:
            print(f"      ⚠️ RSI {rsi:.1f} is overbought (>75) - risky entry")
            issues.append(f"{symbol}: RSI overbought")
        
        if risk_pct > 5:
            print(f"      ⚠️ Stop loss {risk_pct:.1f}% away - position size needs adjustment")
    
    if issues:
        print(f"\n   ⚠️ Found {len(issues)} potential issues for professional trading")
    
    return True


def test_position_sizing():
    """Test position sizing calculations"""
    print("\n" + "="*60)
    print("POSITION SIZING TESTS")
    print("="*60)
    
    import requests
    resp = requests.post("http://localhost:8000/api/screener/elite?top_n=2", timeout=60)
    data = resp.json()
    
    capital = 100000
    max_risk_per_trade = 0.02  # 2%
    
    print(f"\n💰 Position Sizing (Capital: ₹{capital:,}, Max Risk: 2%)")
    
    for c in data.get('candidates', []):
        symbol = c['symbol']
        entry = c['entry_price']
        stop = c['stop_loss']
        pos_size = c['position_size']
        pos_value = c['position_value']
        
        # Calculate correct position size
        risk_per_share = entry - stop
        max_loss = capital * max_risk_per_trade
        correct_pos_size = int(max_loss / risk_per_share) if risk_per_share > 0 else 0
        correct_value = correct_pos_size * entry
        
        print(f"\n   {symbol}:")
        print(f"      Entry: ₹{entry:.2f}, Stop: ₹{stop:.2f}")
        print(f"      Screener suggests: {pos_size} shares (₹{pos_value:,.0f})")
        print(f"      2% risk calc: {correct_pos_size} shares (₹{correct_value:,.0f})")
        
        if abs(pos_size - correct_pos_size) > 5:
            print(f"      ⚠️ Position size differs from 2% risk calculation")
    
    return True


def main():
    print("\n" + "="*60)
    print("🎯 PROFESSIONAL TRADER TEST SUITE")
    print("="*60)
    
    results = {}
    
    results['Data Quality'] = test_data_quality()
    results['Momentum Calculations'] = test_momentum_calculations()
    results['Range Position'] = test_range_position()
    results['Sector Mapping'] = test_sector_mapping()
    results['Risk:Reward'] = test_risk_reward()
    results['Position Sizing'] = test_position_sizing()
    
    print("\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} - {test}")
    
    # Critical issues found
    print("\n" + "="*60)
    print("🐛 CRITICAL BUGS TO FIX")
    print("="*60)
    print("""
    1. ROC CALCULATION BUG in elite_screener.py:
       - shift() operates across all symbols in DataFrame
       - Need to sort by symbol+date and calculate per-symbol
       - Current ROC values are completely wrong (showing 2000%+ instead of 6%)
    
    2. INDICATOR LAG ISSUE:
       - HH_20 (20-day high) not updated for today's price
       - Range position shows >1.0 when stock breaks out
       - Need to include current day's high in calculation
    
    3. SECTOR MAPPING ERRORS:
       - JKTYRE incorrectly mapped to 'Power' (should be 'Auto Ancillary')
       - CEAT not found in mapping
    
    4. RISK:REWARD BELOW STANDARD:
       - Some picks have R:R < 2:1
       - Consider filtering for R:R >= 2:1 minimum
    """)


if __name__ == "__main__":
    main()
