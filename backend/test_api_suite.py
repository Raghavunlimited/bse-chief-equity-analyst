#!/usr/bin/env python3
"""
Comprehensive API Test Suite for NSE Weekly Swing Trader
"""

import requests
import json
import sys
from datetime import datetime

API_BASE = "http://localhost:8000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def test_endpoint(method, endpoint, name, expected_status=200, params=None, json_body=None, timeout=60):
    """Test a single endpoint"""
    url = f"{API_BASE}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, params=params, timeout=timeout)
        else:
            resp = requests.post(url, params=params, json=json_body, timeout=timeout)
        
        status = resp.status_code
        if status == expected_status:
            print(f"  {Colors.GREEN}✅ PASS{Colors.END} {name} (HTTP {status})")
            return True, resp.json() if status == 200 else None
        else:
            print(f"  {Colors.RED}❌ FAIL{Colors.END} {name} (HTTP {status}, expected {expected_status})")
            return False, None
    except requests.exceptions.Timeout:
        print(f"  {Colors.YELLOW}⏱️ TIMEOUT{Colors.END} {name}")
        return False, None
    except Exception as e:
        print(f"  {Colors.RED}❌ ERROR{Colors.END} {name}: {str(e)[:50]}")
        return False, None

def run_tests():
    """Run all API tests"""
    print("\n" + "="*60)
    print(f"{Colors.BLUE}NSE WEEKLY SWING TRADER - API TEST SUITE{Colors.END}")
    print(f"Started: {datetime.now()}")
    print("="*60)
    
    results = {"passed": 0, "failed": 0, "total": 0}
    
    def record(passed):
        results["total"] += 1
        if passed:
            results["passed"] += 1
        else:
            results["failed"] += 1
    
    # === CORE ENDPOINTS ===
    print(f"\n{Colors.BLUE}--- Core Endpoints ---{Colors.END}")
    
    record(test_endpoint("GET", "/", "Health Check")[0])
    record(test_endpoint("GET", "/api/available-dates", "Available Dates")[0])
    record(test_endpoint("GET", "/api/screener/latest", "Latest Screener Results")[0])
    record(test_endpoint("GET", "/api/score-explanation", "Score Explanation")[0])
    record(test_endpoint("GET", "/api/filters/summary", "Filter Summary")[0])
    
    # === SCREENER ENDPOINTS ===
    print(f"\n{Colors.BLUE}--- Screener Endpoints ---{Colors.END}")
    
    # Basic Screener
    passed, data = test_endpoint("POST", "/api/screener/run", "Basic Screener")
    record(passed)
    if passed and data:
        print(f"       └─ Found {len(data.get('results', []))} candidates")
    
    # Enhanced Screener
    passed, data = test_endpoint("POST", "/api/screener/enhanced", "Enhanced Screener")
    record(passed)
    if passed and data:
        print(f"       └─ Found {len(data.get('candidates', []))} candidates")
    
    # Ultimate Screener (takes longer due to complex analysis)
    passed, data = test_endpoint("POST", "/api/screener/ultimate", "Ultimate Screener", timeout=120)
    record(passed)
    if passed and data:
        print(f"       └─ Found {len(data.get('candidates', []))} candidates")
    
    # Elite Screener
    passed, data = test_endpoint("POST", "/api/screener/elite", "Elite Screener", params={"top_n": 2})
    record(passed)
    if passed and data:
        print(f"       └─ Found {len(data.get('candidates', []))} candidates")
        if data.get('candidates'):
            for c in data['candidates'][:2]:
                print(f"          • {c['symbol']}: Score {c['score']}, Target {c['target_price']}")
    
    # Screener Methodologies
    record(test_endpoint("GET", "/api/screener/elite/methodology", "Elite Methodology")[0])
    record(test_endpoint("GET", "/api/screener/ultimate/methodology", "Ultimate Methodology")[0])
    
    # === SECTOR ANALYSIS ===
    print(f"\n{Colors.BLUE}--- Sector Analysis ---{Colors.END}")
    
    passed, data = test_endpoint("GET", "/api/sector-performance", "Sector Performance")
    record(passed)
    if passed and data:
        sectors = data.get('sectors', [])
        print(f"       └─ {len(sectors)} sectors analyzed")
    
    passed, data = test_endpoint("GET", "/api/sector-heatmap", "Sector Heatmap")
    record(passed)
    
    passed, data = test_endpoint("GET", "/api/sector-analysis", "Sector Analysis")
    record(passed)
    
    # === SEASONALITY ===
    print(f"\n{Colors.BLUE}--- Seasonality Analysis ---{Colors.END}")
    
    passed, data = test_endpoint("GET", "/api/seasonality/heatmap", "Seasonality Heatmap")
    record(passed)
    if passed and data:
        print(f"       └─ {len(data.get('sectors', []))} sectors with seasonality data")
    
    passed, data = test_endpoint("GET", "/api/seasonality/recommendations", "Current Month Recommendations")
    record(passed)
    if passed and data:
        recs = data.get('recommendations', [])
        print(f"       └─ {len(recs)} sector recommendations")
    
    # === MARKET & NEWS ===
    print(f"\n{Colors.BLUE}--- Market & News ---{Colors.END}")
    
    passed, data = test_endpoint("GET", "/api/market-regime", "Market Regime")
    record(passed)
    if passed and data:
        regime = data.get('regime', 'Unknown')
        print(f"       └─ Current regime: {regime}")
    
    passed, data = test_endpoint("GET", "/api/news/latest", "Latest News")
    record(passed)
    if passed and data:
        print(f"       └─ {len(data.get('news', []))} news items")
    
    # === STOCK-SPECIFIC ===
    print(f"\n{Colors.BLUE}--- Stock-Specific Endpoints ---{Colors.END}")
    
    test_symbol = "RELIANCE"
    passed, data = test_endpoint("GET", f"/api/chart/{test_symbol}", f"Chart Data ({test_symbol})")
    record(passed)
    if passed and data:
        print(f"       └─ {len(data.get('data', []))} data points")
    
    passed, data = test_endpoint("GET", f"/api/position-size/{test_symbol}", f"Position Size ({test_symbol})")
    record(passed)
    
    passed, data = test_endpoint("GET", f"/api/news/symbol/{test_symbol}", f"Stock News ({test_symbol})")
    record(passed)
    
    # === BACKTEST ===
    print(f"\n{Colors.BLUE}--- Backtest ---{Colors.END}")
    
    passed, data = test_endpoint(
        "POST", "/api/backtest/run", "Run Backtest", 
        json_body={"start_date": "2024-01-01", "end_date": "2024-12-31", "capital": 1000000, "max_positions": 10}
    )
    record(passed)
    if passed and data:
        wr = data.get('win_rate', 0)
        print(f"       └─ Win Rate: {wr:.1f}%")
    
    # === DATA INGESTION ===
    print(f"\n{Colors.BLUE}--- Data Ingestion (Read-Only Test) ---{Colors.END}")
    
    # Just check if endpoint exists, don't actually ingest
    record(test_endpoint("GET", "/api/available-dates", "Check Data Availability")[0])
    
    # === SUMMARY ===
    print("\n" + "="*60)
    print(f"{Colors.BLUE}TEST SUMMARY{Colors.END}")
    print("="*60)
    print(f"  Total Tests:  {results['total']}")
    print(f"  {Colors.GREEN}Passed:{Colors.END}       {results['passed']}")
    print(f"  {Colors.RED}Failed:{Colors.END}       {results['failed']}")
    
    pass_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    
    if pass_rate >= 90:
        print(f"\n  {Colors.GREEN}✅ EXCELLENT: {pass_rate:.1f}% pass rate{Colors.END}")
    elif pass_rate >= 70:
        print(f"\n  {Colors.YELLOW}⚠️ GOOD: {pass_rate:.1f}% pass rate{Colors.END}")
    else:
        print(f"\n  {Colors.RED}❌ NEEDS WORK: {pass_rate:.1f}% pass rate{Colors.END}")
    
    print("="*60)
    
    return results['failed'] == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
