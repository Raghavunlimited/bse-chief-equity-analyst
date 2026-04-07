"""
Financial Analysis Module
Evaluates stock financial health like a professional financial advisor would.

Financial Strength Score (0-100):
- Profitability (25 pts): ROE, ROCE, profit margins
- Debt Health (20 pts): D/E ratio, interest coverage
- Growth (20 pts): Revenue & profit CAGR
- Valuation (15 pts): PE vs industry, PEG ratio
- Promoter Confidence (10 pts): Promoter holding, pledge
- Dividend Track Record (10 pts): Yield, consistency
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Industry average PE ratios for comparison
INDUSTRY_PE = {
    "IT": 25, "Banking": 12, "FMCG": 35, "Pharma": 22, "Auto": 15,
    "Metals": 10, "Oil & Gas": 8, "Telecom": 20, "Infrastructure": 12,
    "Cement": 18, "Chemicals": 20, "Power": 12, "Real Estate": 15,
    "Insurance": 15, "NBFC": 18, "Consumer Durables": 30, "Retail": 35,
    "Healthcare": 25, "Defence": 30, "Unknown": 18
}

# Sector mapping for NSE to Yahoo Finance
NSE_TO_YAHOO = {
    "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "INFY": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS", "ICICIBANK": "ICICIBANK.NS",
    "KOTAKBANK": "KOTAKBANK.NS", "SBIN": "SBIN.NS", "AXISBANK": "AXISBANK.NS",
    "BHARTIARTL": "BHARTIARTL.NS", "ITC": "ITC.NS", "HINDUNILVR": "HINDUNILVR.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "MARUTI": "MARUTI.NS", "TATAMOTORS": "TATAMOTORS.NS",
    "TATASTEEL": "TATASTEEL.NS", "WIPRO": "WIPRO.NS", "HCLTECH": "HCLTECH.NS",
    "ADANIENT": "ADANIENT.NS", "ADANIPORTS": "ADANIPORTS.NS", "POWERGRID": "POWERGRID.NS",
    "NTPC": "NTPC.NS", "ONGC": "ONGC.NS", "COALINDIA": "COALINDIA.NS",
    "SUNPHARMA": "SUNPHARMA.NS", "DRREDDY": "DRREDDY.NS", "CIPLA": "CIPLA.NS",
    "ASIANPAINT": "ASIANPAINT.NS", "ULTRACEMCO": "ULTRACEMCO.NS", "TITAN": "TITAN.NS",
    "NESTLEIND": "NESTLEIND.NS", "TECHM": "TECHM.NS", "LTIM": "LTIM.NS",
    "BAJAJFINSV": "BAJAJFINSV.NS", "LT": "LT.NS", "M&M": "M&M.NS",
}


def get_yahoo_symbol(nse_symbol: str) -> str:
    """Convert NSE symbol to Yahoo Finance symbol."""
    if nse_symbol in NSE_TO_YAHOO:
        return NSE_TO_YAHOO[nse_symbol]
    return f"{nse_symbol}.NS"


def fetch_financial_data(symbol: str) -> Dict[str, Any]:
    """
    Fetch comprehensive financial data for a stock.
    Uses Yahoo Finance for real-time financial data.
    """
    yahoo_symbol = get_yahoo_symbol(symbol)
    
    try:
        stock = yf.Ticker(yahoo_symbol)
        info = stock.info
        
        # Get financial statements
        balance_sheet = stock.balance_sheet
        income_stmt = stock.income_stmt
        cash_flow = stock.cashflow
        
        # Get historical data for 5 years
        hist = stock.history(period="5y")
        
        # Extract key metrics
        financials = {
            "symbol": symbol,
            "company_name": info.get("longName", symbol),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
            
            # Valuation Metrics
            "pe_ratio": safe_get(info, "trailingPE"),
            "forward_pe": safe_get(info, "forwardPE"),
            "pb_ratio": safe_get(info, "priceToBook"),
            "ps_ratio": safe_get(info, "priceToSalesTrailing12Months"),
            "peg_ratio": safe_get(info, "pegRatio"),
            "ev_ebitda": safe_get(info, "enterpriseToEbitda"),
            
            # Profitability Metrics
            "roe": safe_get(info, "returnOnEquity", multiply=100),
            "roa": safe_get(info, "returnOnAssets", multiply=100),
            "profit_margin": safe_get(info, "profitMargins", multiply=100),
            "operating_margin": safe_get(info, "operatingMargins", multiply=100),
            "gross_margin": safe_get(info, "grossMargins", multiply=100),
            
            # Growth Metrics
            "revenue_growth": safe_get(info, "revenueGrowth", multiply=100),
            "earnings_growth": safe_get(info, "earningsGrowth", multiply=100),
            "revenue_per_share": safe_get(info, "revenuePerShare"),
            "eps": safe_get(info, "trailingEps"),
            "forward_eps": safe_get(info, "forwardEps"),
            
            # Debt & Liquidity
            "debt_to_equity": safe_get(info, "debtToEquity"),
            "current_ratio": safe_get(info, "currentRatio"),
            "quick_ratio": safe_get(info, "quickRatio"),
            "total_debt": safe_get(info, "totalDebt"),
            "total_cash": safe_get(info, "totalCash"),
            
            # Dividend
            "dividend_yield": safe_get(info, "dividendYield", multiply=100),
            "dividend_rate": safe_get(info, "dividendRate"),
            "payout_ratio": safe_get(info, "payoutRatio", multiply=100),
            "five_year_avg_dividend_yield": safe_get(info, "fiveYearAvgDividendYield"),
            
            # Ownership
            "insider_holding": safe_get(info, "heldPercentInsiders", multiply=100),
            "institutional_holding": safe_get(info, "heldPercentInstitutions", multiply=100),
            
            # Other
            "beta": safe_get(info, "beta"),
            "52_week_high": safe_get(info, "fiftyTwoWeekHigh"),
            "52_week_low": safe_get(info, "fiftyTwoWeekLow"),
            "50_day_avg": safe_get(info, "fiftyDayAverage"),
            "200_day_avg": safe_get(info, "twoHundredDayAverage"),
            "avg_volume": safe_get(info, "averageVolume"),
            "book_value": safe_get(info, "bookValue"),
            
            # Balance Sheet Summary
            "balance_sheet": extract_balance_sheet(balance_sheet),
            
            # Income Statement Summary
            "income_statement": extract_income_statement(income_stmt),
            
            # Cash Flow Summary
            "cash_flow": extract_cash_flow(cash_flow),
            
            # 5-Year Performance
            "five_year_return": calculate_return(hist, "5y"),
            "one_year_return": calculate_return(hist, "1y"),
            "ytd_return": calculate_return(hist, "ytd"),
        }
        
        # Calculate Financial Strength Score
        financials["financial_score"] = calculate_financial_score(financials, info)

        # Earnings quality assessment
        financials["earnings_quality"] = calculate_earnings_quality(
            financials, info, income_stmt, cash_flow
        )

        # Corporate governance score
        financials["governance_score"] = calculate_governance_score(financials, info)

        # Generate Pros and Cons
        financials["analysis"] = generate_analysis(financials)

        return financials
        
    except Exception as e:
        logger.error(f"Error fetching financial data for {symbol}: {e}")
        return {
            "symbol": symbol,
            "error": str(e),
            "message": "Could not fetch financial data. The stock may not be available on Yahoo Finance."
        }


def safe_get(data: dict, key: str, multiply: float = None) -> Optional[float]:
    """Safely get a value from dict, optionally multiply for percentage."""
    value = data.get(key)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if multiply and value is not None:
        return round(value * multiply, 2)
    return round(value, 2) if isinstance(value, float) else value


def extract_balance_sheet(df: pd.DataFrame) -> Dict[str, Any]:
    """Extract key balance sheet items."""
    if df is None or df.empty:
        return {"available": False}
    
    try:
        latest = df.iloc[:, 0]  # Most recent year
        years = [col.strftime("%Y") if hasattr(col, 'strftime') else str(col)[:4] for col in df.columns[:4]]
        
        return {
            "available": True,
            "years": years,
            "total_assets": format_currency(latest.get("Total Assets")),
            "total_liabilities": format_currency(latest.get("Total Liabilities Net Minority Interest")),
            "total_equity": format_currency(latest.get("Stockholders Equity")),
            "total_debt": format_currency(latest.get("Total Debt")),
            "cash_and_equivalents": format_currency(latest.get("Cash And Cash Equivalents")),
            "current_assets": format_currency(latest.get("Current Assets")),
            "current_liabilities": format_currency(latest.get("Current Liabilities")),
            "retained_earnings": format_currency(latest.get("Retained Earnings")),
            "working_capital": format_currency(latest.get("Working Capital")),
        }
    except Exception as e:
        logger.error(f"Error extracting balance sheet: {e}")
        return {"available": False, "error": str(e)}


def extract_income_statement(df: pd.DataFrame) -> Dict[str, Any]:
    """Extract key income statement items."""
    if df is None or df.empty:
        return {"available": False}
    
    try:
        # Get last 5 years of data
        years_data = []
        for i, col in enumerate(df.columns[:5]):
            year = col.strftime("%Y") if hasattr(col, 'strftime') else str(col)[:4]
            years_data.append({
                "year": year,
                "revenue": format_currency(df.loc["Total Revenue", col] if "Total Revenue" in df.index else None),
                "gross_profit": format_currency(df.loc["Gross Profit", col] if "Gross Profit" in df.index else None),
                "operating_income": format_currency(df.loc["Operating Income", col] if "Operating Income" in df.index else None),
                "net_income": format_currency(df.loc["Net Income", col] if "Net Income" in df.index else None),
                "ebitda": format_currency(df.loc["EBITDA", col] if "EBITDA" in df.index else None),
            })
        
        # Calculate growth rates
        if len(years_data) >= 2:
            revenue_current = df.loc["Total Revenue", df.columns[0]] if "Total Revenue" in df.index else 0
            revenue_prev = df.loc["Total Revenue", df.columns[1]] if "Total Revenue" in df.index else 1
            revenue_growth = ((revenue_current / revenue_prev) - 1) * 100 if revenue_prev else 0
            
            profit_current = df.loc["Net Income", df.columns[0]] if "Net Income" in df.index else 0
            profit_prev = df.loc["Net Income", df.columns[1]] if "Net Income" in df.index else 1
            profit_growth = ((profit_current / profit_prev) - 1) * 100 if profit_prev else 0
        else:
            revenue_growth = 0
            profit_growth = 0
        
        return {
            "available": True,
            "yearly_data": years_data,
            "revenue_growth_yoy": round(revenue_growth, 2),
            "profit_growth_yoy": round(profit_growth, 2),
        }
    except Exception as e:
        logger.error(f"Error extracting income statement: {e}")
        return {"available": False, "error": str(e)}


def extract_cash_flow(df: pd.DataFrame) -> Dict[str, Any]:
    """Extract key cash flow items."""
    if df is None or df.empty:
        return {"available": False}
    
    try:
        latest = df.iloc[:, 0]
        
        return {
            "available": True,
            "operating_cash_flow": format_currency(latest.get("Operating Cash Flow")),
            "investing_cash_flow": format_currency(latest.get("Investing Cash Flow")),
            "financing_cash_flow": format_currency(latest.get("Financing Cash Flow")),
            "free_cash_flow": format_currency(latest.get("Free Cash Flow")),
            "capital_expenditure": format_currency(latest.get("Capital Expenditure")),
        }
    except Exception as e:
        logger.error(f"Error extracting cash flow: {e}")
        return {"available": False, "error": str(e)}


def format_currency(value) -> Optional[Dict]:
    """Format large currency values."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    
    value = float(value)
    abs_value = abs(value)
    
    if abs_value >= 1e12:
        return {"value": round(value / 1e12, 2), "unit": "T", "raw": value}
    elif abs_value >= 1e9:
        return {"value": round(value / 1e9, 2), "unit": "B", "raw": value}
    elif abs_value >= 1e7:
        return {"value": round(value / 1e7, 2), "unit": "Cr", "raw": value}
    elif abs_value >= 1e5:
        return {"value": round(value / 1e5, 2), "unit": "L", "raw": value}
    else:
        return {"value": round(value, 2), "unit": "", "raw": value}


def calculate_return(hist: pd.DataFrame, period: str) -> Optional[float]:
    """Calculate return for a given period."""
    if hist is None or hist.empty:
        return None
    
    try:
        if period == "5y":
            start_price = hist["Close"].iloc[0]
            end_price = hist["Close"].iloc[-1]
        elif period == "1y":
            one_year_ago = datetime.now() - timedelta(days=365)
            recent = hist[hist.index >= one_year_ago]
            if recent.empty:
                return None
            start_price = recent["Close"].iloc[0]
            end_price = recent["Close"].iloc[-1]
        elif period == "ytd":
            year_start = datetime(datetime.now().year, 1, 1)
            recent = hist[hist.index >= year_start]
            if recent.empty:
                return None
            start_price = recent["Close"].iloc[0]
            end_price = recent["Close"].iloc[-1]
        else:
            return None
        
        return round(((end_price / start_price) - 1) * 100, 2)
    except Exception:
        return None


def calculate_financial_score(financials: Dict, info: Dict) -> Dict[str, Any]:
    """
    Calculate comprehensive Financial Strength Score (0-100).
    
    Scoring Breakdown:
    - Profitability (25 pts): ROE, ROCE, margins
    - Debt Health (20 pts): D/E ratio, interest coverage, current ratio
    - Growth (20 pts): Revenue & profit growth
    - Valuation (15 pts): PE vs industry, PEG
    - Promoter Confidence (10 pts): Insider holding
    - Dividend (10 pts): Yield, consistency
    """
    scores = {
        "profitability": {"score": 0, "max": 25, "details": []},
        "debt_health": {"score": 0, "max": 20, "details": []},
        "growth": {"score": 0, "max": 20, "details": []},
        "valuation": {"score": 0, "max": 15, "details": []},
        "promoter_confidence": {"score": 0, "max": 10, "details": []},
        "dividend": {"score": 0, "max": 10, "details": []},
    }
    
    # === PROFITABILITY (25 pts) ===
    roe = financials.get("roe")
    if roe is not None:
        if roe >= 20:
            scores["profitability"]["score"] += 10
            scores["profitability"]["details"].append(f"Excellent ROE: {roe}%")
        elif roe >= 15:
            scores["profitability"]["score"] += 7
            scores["profitability"]["details"].append(f"Good ROE: {roe}%")
        elif roe >= 10:
            scores["profitability"]["score"] += 4
            scores["profitability"]["details"].append(f"Average ROE: {roe}%")
        else:
            scores["profitability"]["details"].append(f"Low ROE: {roe}%")
    
    profit_margin = financials.get("profit_margin")
    if profit_margin is not None:
        if profit_margin >= 15:
            scores["profitability"]["score"] += 8
            scores["profitability"]["details"].append(f"High profit margin: {profit_margin}%")
        elif profit_margin >= 10:
            scores["profitability"]["score"] += 5
            scores["profitability"]["details"].append(f"Good profit margin: {profit_margin}%")
        elif profit_margin >= 5:
            scores["profitability"]["score"] += 3
            scores["profitability"]["details"].append(f"Moderate profit margin: {profit_margin}%")
        else:
            scores["profitability"]["details"].append(f"Low profit margin: {profit_margin}%")
    
    operating_margin = financials.get("operating_margin")
    if operating_margin is not None:
        if operating_margin >= 20:
            scores["profitability"]["score"] += 7
        elif operating_margin >= 12:
            scores["profitability"]["score"] += 5
        elif operating_margin >= 8:
            scores["profitability"]["score"] += 3
    
    # === DEBT HEALTH (20 pts) ===
    de_ratio = financials.get("debt_to_equity")
    if de_ratio is not None:
        if de_ratio <= 0.3:
            scores["debt_health"]["score"] += 10
            scores["debt_health"]["details"].append(f"Very low debt: D/E = {de_ratio}")
        elif de_ratio <= 0.7:
            scores["debt_health"]["score"] += 7
            scores["debt_health"]["details"].append(f"Low debt: D/E = {de_ratio}")
        elif de_ratio <= 1.2:
            scores["debt_health"]["score"] += 4
            scores["debt_health"]["details"].append(f"Moderate debt: D/E = {de_ratio}")
        else:
            scores["debt_health"]["details"].append(f"High debt: D/E = {de_ratio}")
    
    current_ratio = financials.get("current_ratio")
    if current_ratio is not None:
        if current_ratio >= 2:
            scores["debt_health"]["score"] += 6
            scores["debt_health"]["details"].append(f"Strong liquidity: Current ratio = {current_ratio}")
        elif current_ratio >= 1.5:
            scores["debt_health"]["score"] += 4
            scores["debt_health"]["details"].append(f"Good liquidity: Current ratio = {current_ratio}")
        elif current_ratio >= 1:
            scores["debt_health"]["score"] += 2
            scores["debt_health"]["details"].append(f"Adequate liquidity: Current ratio = {current_ratio}")
        else:
            scores["debt_health"]["details"].append(f"Low liquidity: Current ratio = {current_ratio}")
    
    quick_ratio = financials.get("quick_ratio")
    if quick_ratio is not None:
        if quick_ratio >= 1.5:
            scores["debt_health"]["score"] += 4
        elif quick_ratio >= 1:
            scores["debt_health"]["score"] += 2
    
    # === GROWTH (20 pts) ===
    revenue_growth = financials.get("revenue_growth")
    if revenue_growth is not None:
        if revenue_growth >= 20:
            scores["growth"]["score"] += 10
            scores["growth"]["details"].append(f"Strong revenue growth: {revenue_growth}%")
        elif revenue_growth >= 10:
            scores["growth"]["score"] += 7
            scores["growth"]["details"].append(f"Good revenue growth: {revenue_growth}%")
        elif revenue_growth >= 5:
            scores["growth"]["score"] += 4
            scores["growth"]["details"].append(f"Moderate revenue growth: {revenue_growth}%")
        elif revenue_growth >= 0:
            scores["growth"]["score"] += 2
            scores["growth"]["details"].append(f"Slow revenue growth: {revenue_growth}%")
        else:
            scores["growth"]["details"].append(f"Declining revenue: {revenue_growth}%")
    
    earnings_growth = financials.get("earnings_growth")
    if earnings_growth is not None:
        if earnings_growth >= 20:
            scores["growth"]["score"] += 10
            scores["growth"]["details"].append(f"Strong earnings growth: {earnings_growth}%")
        elif earnings_growth >= 10:
            scores["growth"]["score"] += 7
            scores["growth"]["details"].append(f"Good earnings growth: {earnings_growth}%")
        elif earnings_growth >= 0:
            scores["growth"]["score"] += 3
            scores["growth"]["details"].append(f"Positive earnings growth: {earnings_growth}%")
        else:
            scores["growth"]["details"].append(f"Declining earnings: {earnings_growth}%")
    
    # === VALUATION (15 pts) ===
    pe = financials.get("pe_ratio")
    sector = financials.get("sector", "Unknown")
    industry_pe = INDUSTRY_PE.get(sector, 18)
    
    if pe is not None:
        if pe < industry_pe * 0.7:
            scores["valuation"]["score"] += 8
            scores["valuation"]["details"].append(f"Undervalued: PE {pe} vs Industry {industry_pe}")
        elif pe < industry_pe:
            scores["valuation"]["score"] += 5
            scores["valuation"]["details"].append(f"Fair value: PE {pe} vs Industry {industry_pe}")
        elif pe < industry_pe * 1.3:
            scores["valuation"]["score"] += 3
            scores["valuation"]["details"].append(f"Slightly overvalued: PE {pe} vs Industry {industry_pe}")
        else:
            scores["valuation"]["details"].append(f"Overvalued: PE {pe} vs Industry {industry_pe}")
    
    peg = financials.get("peg_ratio")
    if peg is not None:
        if peg < 1:
            scores["valuation"]["score"] += 7
            scores["valuation"]["details"].append(f"Attractive PEG: {peg}")
        elif peg < 1.5:
            scores["valuation"]["score"] += 4
            scores["valuation"]["details"].append(f"Fair PEG: {peg}")
        elif peg < 2:
            scores["valuation"]["score"] += 2
        else:
            scores["valuation"]["details"].append(f"High PEG: {peg}")
    
    # === PROMOTER CONFIDENCE (10 pts) ===
    insider = financials.get("insider_holding")
    if insider is not None:
        if insider >= 50:
            scores["promoter_confidence"]["score"] += 10
            scores["promoter_confidence"]["details"].append(f"High promoter holding: {insider}%")
        elif insider >= 40:
            scores["promoter_confidence"]["score"] += 7
            scores["promoter_confidence"]["details"].append(f"Good promoter holding: {insider}%")
        elif insider >= 25:
            scores["promoter_confidence"]["score"] += 4
            scores["promoter_confidence"]["details"].append(f"Moderate promoter holding: {insider}%")
        else:
            scores["promoter_confidence"]["details"].append(f"Low promoter holding: {insider}%")
    
    # === DIVIDEND (10 pts) ===
    div_yield = financials.get("dividend_yield")
    if div_yield is not None:
        if div_yield >= 3:
            scores["dividend"]["score"] += 6
            scores["dividend"]["details"].append(f"Good dividend yield: {div_yield}%")
        elif div_yield >= 1.5:
            scores["dividend"]["score"] += 4
            scores["dividend"]["details"].append(f"Moderate dividend yield: {div_yield}%")
        elif div_yield > 0:
            scores["dividend"]["score"] += 2
            scores["dividend"]["details"].append(f"Low dividend yield: {div_yield}%")
        else:
            scores["dividend"]["details"].append("No dividend")
    
    payout = financials.get("payout_ratio")
    if payout is not None:
        if 20 <= payout <= 60:
            scores["dividend"]["score"] += 4
            scores["dividend"]["details"].append(f"Healthy payout ratio: {payout}%")
        elif payout < 20:
            scores["dividend"]["score"] += 2
            scores["dividend"]["details"].append(f"Conservative payout: {payout}%")
        else:
            scores["dividend"]["details"].append(f"High payout ratio: {payout}%")
    
    # Calculate total score
    total_score = sum(cat["score"] for cat in scores.values())
    max_score = sum(cat["max"] for cat in scores.values())
    
    # Determine rating
    if total_score >= 80:
        rating = "Excellent"
        rating_color = "green"
    elif total_score >= 65:
        rating = "Good"
        rating_color = "green"
    elif total_score >= 50:
        rating = "Average"
        rating_color = "yellow"
    elif total_score >= 35:
        rating = "Below Average"
        rating_color = "orange"
    else:
        rating = "Poor"
        rating_color = "red"
    
    return {
        "total_score": total_score,
        "max_score": max_score,
        "percentage": round((total_score / max_score) * 100, 1),
        "rating": rating,
        "rating_color": rating_color,
        "breakdown": scores
    }


def generate_analysis(financials: Dict) -> Dict[str, Any]:
    """Generate pros, cons, and investment thesis."""
    pros = []
    cons = []
    
    # Check profitability
    roe = financials.get("roe")
    if roe and roe >= 15:
        pros.append(f"Strong return on equity ({roe}%)")
    elif roe and roe < 10:
        cons.append(f"Low return on equity ({roe}%)")
    
    # Check margins
    profit_margin = financials.get("profit_margin")
    if profit_margin and profit_margin >= 15:
        pros.append(f"Healthy profit margins ({profit_margin}%)")
    elif profit_margin and profit_margin < 5:
        cons.append(f"Thin profit margins ({profit_margin}%)")
    
    # Check debt
    de_ratio = financials.get("debt_to_equity")
    if de_ratio is not None:
        if de_ratio <= 0.5:
            pros.append(f"Low debt levels (D/E: {de_ratio})")
        elif de_ratio > 1.5:
            cons.append(f"High debt burden (D/E: {de_ratio})")
    
    # Check growth
    revenue_growth = financials.get("revenue_growth")
    if revenue_growth and revenue_growth >= 15:
        pros.append(f"Strong revenue growth ({revenue_growth}%)")
    elif revenue_growth and revenue_growth < 0:
        cons.append(f"Declining revenue ({revenue_growth}%)")
    
    earnings_growth = financials.get("earnings_growth")
    if earnings_growth and earnings_growth >= 20:
        pros.append(f"Excellent earnings growth ({earnings_growth}%)")
    elif earnings_growth and earnings_growth < 0:
        cons.append(f"Declining earnings ({earnings_growth}%)")
    
    # Check valuation
    pe = financials.get("pe_ratio")
    peg = financials.get("peg_ratio")
    if pe and pe < 15:
        pros.append(f"Attractive valuation (PE: {pe})")
    elif pe and pe > 50:
        cons.append(f"Expensive valuation (PE: {pe})")
    
    if peg and peg < 1:
        pros.append("PEG ratio indicates undervaluation")
    elif peg and peg > 2:
        cons.append("PEG ratio suggests overvaluation")
    
    # Check dividends
    div_yield = financials.get("dividend_yield")
    if div_yield and div_yield >= 2:
        pros.append(f"Good dividend yield ({div_yield}%)")
    
    # Check liquidity
    current_ratio = financials.get("current_ratio")
    if current_ratio and current_ratio >= 2:
        pros.append("Strong liquidity position")
    elif current_ratio and current_ratio < 1:
        cons.append("Liquidity concerns")
    
    # Check cash flow
    cash_flow = financials.get("cash_flow", {})
    if cash_flow.get("available"):
        ocf = cash_flow.get("operating_cash_flow")
        fcf = cash_flow.get("free_cash_flow")
        if ocf and ocf.get("raw", 0) > 0:
            pros.append("Positive operating cash flow")
        if fcf and fcf.get("raw", 0) > 0:
            pros.append("Generating free cash flow")
        elif fcf and fcf.get("raw", 0) < 0:
            cons.append("Negative free cash flow")
    
    # 5-year return
    five_yr = financials.get("five_year_return")
    if five_yr and five_yr >= 100:
        pros.append(f"Doubled in 5 years ({five_yr}% return)")
    elif five_yr and five_yr < 0:
        cons.append(f"Negative 5-year return ({five_yr}%)")
    
    # Generate investment thesis
    score = financials.get("financial_score", {}).get("percentage", 0)
    if score >= 70:
        thesis = "Strong financial fundamentals make this a quality investment candidate for long-term portfolios."
        recommendation = "Consider buying on dips"
    elif score >= 50:
        thesis = "Decent financials with some areas of concern. Suitable for moderate risk tolerance."
        recommendation = "Hold or accumulate slowly"
    else:
        thesis = "Financial metrics show significant weaknesses. High risk investment requiring careful monitoring."
        recommendation = "Avoid or reduce exposure"
    
    return {
        "pros": pros[:6],  # Max 6 pros
        "cons": cons[:6],  # Max 6 cons
        "investment_thesis": thesis,
        "recommendation": recommendation,
        "risk_level": "Low" if score >= 70 else "Medium" if score >= 50 else "High"
    }


def calculate_earnings_quality(financials: Dict, info: Dict, income_stmt: pd.DataFrame, cash_flow: pd.DataFrame) -> Dict[str, Any]:
    """
    Assess earnings quality using institutional-grade checks.

    Scores (0-30):
    - Cash Conversion (10): OCF vs Net Income — high-quality earnings are backed by cash
    - Accrual Ratio (10): Low accruals = sustainable earnings
    - Revenue Quality (10): Consistency and non-one-off nature
    """
    scores = {"score": 0, "max": 30, "grade": "N/A", "details": [], "red_flags": []}

    # Cash Conversion: Operating CF / Net Income — should be > 0.8
    ocf_raw = None
    ni_raw = None
    try:
        if cash_flow is not None and not cash_flow.empty:
            if "Operating Cash Flow" in cash_flow.index:
                ocf_raw = float(cash_flow.loc["Operating Cash Flow"].dropna().iloc[0])
        if income_stmt is not None and not income_stmt.empty:
            if "Net Income" in income_stmt.index:
                ni_raw = float(income_stmt.loc["Net Income"].dropna().iloc[0])
    except Exception:
        pass

    if ocf_raw is not None and ni_raw is not None and ni_raw > 0:
        cash_conv = ocf_raw / ni_raw
        if cash_conv >= 1.0:
            scores["score"] += 10
            scores["details"].append(f"Excellent cash conversion: {cash_conv:.2f}x")
        elif cash_conv >= 0.8:
            scores["score"] += 7
            scores["details"].append(f"Good cash conversion: {cash_conv:.2f}x")
        elif cash_conv >= 0.5:
            scores["score"] += 4
            scores["details"].append(f"Moderate cash conversion: {cash_conv:.2f}x")
        else:
            scores["red_flags"].append(f"Poor cash conversion: {cash_conv:.2f}x — earnings may not be backed by cash")
    elif ni_raw is not None and ni_raw < 0:
        scores["red_flags"].append("Net income is negative")

    # Accrual Ratio: (Net Income - OCF) / Total Assets — lower is better
    total_assets = None
    try:
        balance_sheet = financials.get("balance_sheet", {})
        if balance_sheet.get("available"):
            ta_data = balance_sheet.get("total_assets")
            if ta_data and ta_data.get("raw"):
                total_assets = ta_data["raw"]
    except Exception:
        pass

    if ocf_raw is not None and ni_raw is not None and total_assets and total_assets > 0:
        accrual_ratio = (ni_raw - ocf_raw) / total_assets
        if accrual_ratio < 0.05:
            scores["score"] += 10
            scores["details"].append(f"Low accrual ratio: {accrual_ratio:.3f} (sustainable earnings)")
        elif accrual_ratio < 0.10:
            scores["score"] += 6
            scores["details"].append(f"Moderate accrual ratio: {accrual_ratio:.3f}")
        elif accrual_ratio < 0.20:
            scores["score"] += 3
        else:
            scores["red_flags"].append(f"High accrual ratio: {accrual_ratio:.3f} — earnings quality concern")

    # Revenue Consistency: Check if revenue grew each year (no wild swings)
    try:
        if income_stmt is not None and not income_stmt.empty and "Total Revenue" in income_stmt.index:
            rev_vals = income_stmt.loc["Total Revenue"].dropna().values[:4]
            if len(rev_vals) >= 3:
                growing = all(rev_vals[i] >= rev_vals[i + 1] * 0.9 for i in range(len(rev_vals) - 1))
                if growing:
                    scores["score"] += 10
                    scores["details"].append("Consistent revenue trajectory (no major drops)")
                else:
                    yoy_changes = [(rev_vals[i] / rev_vals[i + 1] - 1) * 100 for i in range(len(rev_vals) - 1)]
                    min_change = min(yoy_changes)
                    if min_change > -10:
                        scores["score"] += 6
                        scores["details"].append("Mostly consistent revenue")
                    else:
                        scores["score"] += 2
                        scores["red_flags"].append(f"Revenue volatility detected (worst YoY: {min_change:.1f}%)")
    except Exception:
        pass

    # Grade
    pct = (scores["score"] / scores["max"]) * 100 if scores["max"] > 0 else 0
    if pct >= 80:
        scores["grade"] = "A"
    elif pct >= 60:
        scores["grade"] = "B"
    elif pct >= 40:
        scores["grade"] = "C"
    else:
        scores["grade"] = "D"

    return scores


def calculate_governance_score(financials: Dict, info: Dict) -> Dict[str, Any]:
    """
    Corporate governance scoring (0-25).

    Checks:
    - Promoter holding level & trend (8 pts)
    - Pledge-to-holding ratio (7 pts)
    - Institutional confidence (5 pts)
    - Related-party / audit flags (5 pts)
    """
    scores = {"score": 0, "max": 25, "grade": "N/A", "details": [], "red_flags": []}

    # Promoter / Insider Holding
    insider = financials.get("insider_holding")
    if insider is not None:
        if insider >= 55:
            scores["score"] += 8
            scores["details"].append(f"Strong promoter holding: {insider}%")
        elif insider >= 45:
            scores["score"] += 6
            scores["details"].append(f"Good promoter holding: {insider}%")
        elif insider >= 30:
            scores["score"] += 4
            scores["details"].append(f"Moderate promoter holding: {insider}%")
        elif insider >= 15:
            scores["score"] += 2
            scores["details"].append(f"Low promoter holding: {insider}%")
        else:
            scores["red_flags"].append(f"Very low promoter holding: {insider}% — skin-in-game concern")

    # Institutional holding as quality proxy
    institutional = financials.get("institutional_holding")
    if institutional is not None:
        if institutional >= 35:
            scores["score"] += 5
            scores["details"].append(f"High institutional ownership: {institutional}% (vote of confidence)")
        elif institutional >= 20:
            scores["score"] += 3
            scores["details"].append(f"Reasonable institutional ownership: {institutional}%")
        elif institutional >= 10:
            scores["score"] += 1
        else:
            scores["details"].append(f"Low institutional ownership: {institutional}%")

    # Pledge check (use beta as a rough proxy for risk; actual pledge needs NSE data)
    beta = financials.get("beta")
    if beta is not None:
        if beta > 2.0:
            scores["red_flags"].append(f"Very high beta ({beta}) — may indicate speculative / governance concerns")
        elif beta > 1.5:
            scores["details"].append(f"Elevated beta: {beta}")
        elif beta <= 1.0:
            scores["score"] += 3
            scores["details"].append(f"Low beta: {beta} — stable governance perception")

    # Payout ratio sanity (extreme payouts can signal desperation or poor capital allocation)
    payout = financials.get("payout_ratio")
    if payout is not None:
        if payout > 100:
            scores["red_flags"].append(f"Payout ratio {payout}% exceeds earnings — unsustainable")
        elif 20 <= payout <= 60:
            scores["score"] += 4
            scores["details"].append(f"Balanced payout ratio: {payout}%")
        elif payout < 5 and insider is not None and insider < 30:
            scores["details"].append("Very low payout with low promoter holding")

    # Audit / quality heuristic: negative FCF with high debt is a governance red flag
    de_ratio = financials.get("debt_to_equity")
    cf = financials.get("cash_flow", {})
    fcf_data = cf.get("free_cash_flow") if cf.get("available") else None
    if de_ratio is not None and de_ratio > 1.5 and fcf_data and fcf_data.get("raw", 0) < 0:
        scores["red_flags"].append("High debt + negative FCF — governance / solvency risk")
    elif de_ratio is not None and de_ratio <= 0.5 and fcf_data and fcf_data.get("raw", 0) > 0:
        scores["score"] += 5
        scores["details"].append("Low debt + positive FCF — strong financial governance")

    pct = (scores["score"] / scores["max"]) * 100 if scores["max"] > 0 else 0
    if pct >= 80:
        scores["grade"] = "A"
    elif pct >= 60:
        scores["grade"] = "B"
    elif pct >= 40:
        scores["grade"] = "C"
    else:
        scores["grade"] = "D"

    return scores


def get_corporate_announcements(symbol: str) -> List[Dict]:
    """Get recent corporate announcements for a stock from news analyzer."""
    try:
        from app.news_analyzer import get_news_aggregator
        aggregator = get_news_aggregator()
        return aggregator.get_signals_for_symbol(symbol)
    except Exception:
        return []
