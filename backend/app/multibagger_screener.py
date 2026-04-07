"""
Multibagger Screener - Long-Term Wealth Creation Module

Identifies stocks with potential for 2-10x returns over 3-5 years.
Uses fundamental analysis to find quality growth companies at reasonable valuations.

Scoring System (100 points total):
- Growth (25 pts): Revenue CAGR, EPS growth, earnings consistency
- Profitability (25 pts): ROE, ROCE, profit margins
- Quality (20 pts): Low debt, strong cash flows, good management
- Value (15 pts): PEG ratio, PE vs industry, fair value discount
- Moat (15 pts): Promoter holding, competitive advantages

Target Criteria for Multibaggers:
- ROE consistently > 15%
- Revenue CAGR > 15% for 3 years 
- Debt/Equity < 0.5
- Promoter holding > 50%
- PEG ratio < 1.5
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Industry benchmarks for comparison
INDUSTRY_BENCHMARKS = {
    "IT": {"pe": 25, "roe": 20, "growth": 15},
    "Banking": {"pe": 12, "roe": 14, "growth": 12},
    "FMCG": {"pe": 35, "roe": 25, "growth": 10},
    "Pharma": {"pe": 22, "roe": 15, "growth": 12},
    "Auto": {"pe": 15, "roe": 12, "growth": 10},
    "Chemicals": {"pe": 20, "roe": 15, "growth": 15},
    "Finance": {"pe": 18, "roe": 15, "growth": 15},
    "Infrastructure": {"pe": 15, "roe": 12, "growth": 12},
    "Healthcare": {"pe": 25, "roe": 15, "growth": 12},
    "Defence": {"pe": 30, "roe": 15, "growth": 20},
    "Unknown": {"pe": 18, "roe": 12, "growth": 10}
}

# Blue chip quality stocks (for validation)
KNOWN_QUALITY_STOCKS = [
    "TCS", "INFY", "HDFCBANK", "ICICIBANK", "RELIANCE", "BAJFINANCE",
    "ASIANPAINT", "TITAN", "NESTLEIND", "PIDILITIND", "DMART", "HDFC",
    "KOTAKBANK", "HINDUNILVR", "MARUTI", "ULTRACEMCO", "BRITANNIA"
]


def get_yahoo_symbol(nse_symbol: str) -> str:
    """Convert NSE symbol to Yahoo Finance symbol."""
    return f"{nse_symbol}.NS"


def fetch_stock_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Fetch comprehensive fundamental data for a stock.
    Returns key metrics for multibagger scoring.
    """
    yahoo_symbol = get_yahoo_symbol(symbol)
    
    try:
        stock = yf.Ticker(yahoo_symbol)
        info = stock.info
        
        # Get financial statements
        balance_sheet = stock.balance_sheet
        income_stmt = stock.income_stmt
        cash_flow = stock.cashflow
        
        # Extract key metrics
        fundamentals = {
            "symbol": symbol,
            "company_name": info.get("longName", symbol),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
            
            # Growth Metrics
            "revenue_growth": safe_get(info, "revenueGrowth", multiply=100),
            "earnings_growth": safe_get(info, "earningsGrowth", multiply=100),
            "eps": safe_get(info, "trailingEps"),
            "forward_eps": safe_get(info, "forwardEps"),
            
            # Profitability Metrics
            "roe": safe_get(info, "returnOnEquity", multiply=100),
            "roa": safe_get(info, "returnOnAssets", multiply=100),
            "profit_margin": safe_get(info, "profitMargins", multiply=100),
            "operating_margin": safe_get(info, "operatingMargins", multiply=100),
            "gross_margin": safe_get(info, "grossMargins", multiply=100),
            
            # Valuation
            "pe_ratio": safe_get(info, "trailingPE"),
            "forward_pe": safe_get(info, "forwardPE"),
            "pb_ratio": safe_get(info, "priceToBook"),
            "peg_ratio": safe_get(info, "pegRatio"),
            "ev_ebitda": safe_get(info, "enterpriseToEbitda"),
            
            # Debt & Quality
            "debt_to_equity": safe_get(info, "debtToEquity"),
            "current_ratio": safe_get(info, "currentRatio"),
            "quick_ratio": safe_get(info, "quickRatio"),
            "total_debt": safe_get(info, "totalDebt"),
            "total_cash": safe_get(info, "totalCash"),
            "free_cash_flow": safe_get(info, "freeCashflow"),
            
            # Ownership
            "insider_holding": safe_get(info, "heldPercentInsiders", multiply=100),
            "institutional_holding": safe_get(info, "heldPercentInstitutions", multiply=100),
            
            # Dividend
            "dividend_yield": safe_get(info, "dividendYield", multiply=100),
            "payout_ratio": safe_get(info, "payoutRatio", multiply=100),
            
            # Price Performance
            "52_week_high": safe_get(info, "fiftyTwoWeekHigh"),
            "52_week_low": safe_get(info, "fiftyTwoWeekLow"),
            "book_value": safe_get(info, "bookValue"),
            
            # Calculated metrics
            "revenue_cagr_3y": calculate_cagr(income_stmt, "Total Revenue", years=3),
            "profit_cagr_3y": calculate_cagr(income_stmt, "Net Income", years=3),
            "fcf_positive": is_fcf_positive(cash_flow),
            "earnings_consistent": check_earnings_consistency(income_stmt),
        }
        
        # Calculate distance from 52-week high
        if fundamentals["52_week_high"] and fundamentals["current_price"]:
            fundamentals["from_52w_high"] = (
                (fundamentals["52_week_high"] - fundamentals["current_price"]) 
                / fundamentals["52_week_high"] * 100
            )
        else:
            fundamentals["from_52w_high"] = None
        
        return fundamentals
        
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol}: {e}")
        return {
            "symbol": symbol,
            "error": str(e),
            "message": f"Could not fetch data for {symbol}"
        }


def safe_get(data: dict, key: str, multiply: float = None) -> Optional[float]:
    """Safely get a value from dict, optionally multiply for percentage."""
    value = data.get(key)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if multiply and value is not None:
        return round(value * multiply, 2)
    return round(value, 2) if isinstance(value, float) else value


def calculate_cagr(income_stmt: pd.DataFrame, metric: str, years: int = 3) -> Optional[float]:
    """Calculate CAGR for a given metric over specified years."""
    if income_stmt is None or income_stmt.empty:
        return None
    
    try:
        if metric not in income_stmt.index:
            return None
        
        values = income_stmt.loc[metric].dropna().values
        if len(values) < 2:
            return None
        
        # Get first and last values (most recent first in yfinance)
        end_value = values[0]
        start_value = values[min(years, len(values) - 1)]
        
        if start_value <= 0 or end_value <= 0:
            return None
        
        actual_years = min(years, len(values) - 1)
        cagr = ((end_value / start_value) ** (1 / actual_years) - 1) * 100
        
        return round(cagr, 2)
    except Exception:
        return None


def is_fcf_positive(cash_flow: pd.DataFrame) -> bool:
    """Check if Free Cash Flow is positive in recent years."""
    if cash_flow is None or cash_flow.empty:
        return False
    
    try:
        fcf_row = None
        for metric in ["Free Cash Flow", "Operating Cash Flow"]:
            if metric in cash_flow.index:
                fcf_row = cash_flow.loc[metric]
                break
        
        if fcf_row is None:
            return False
        
        # Check if at least 2 of last 3 years are positive
        recent_values = fcf_row.dropna().values[:3]
        positive_count = sum(1 for v in recent_values if v > 0)
        return positive_count >= 2
    except Exception:
        return False


def check_earnings_consistency(income_stmt: pd.DataFrame) -> bool:
    """Check if company has consistent positive earnings."""
    if income_stmt is None or income_stmt.empty:
        return False
    
    try:
        if "Net Income" not in income_stmt.index:
            return False
        
        net_income = income_stmt.loc["Net Income"].dropna().values[:4]
        positive_count = sum(1 for v in net_income if v > 0)
        return positive_count >= 3  # At least 3 of 4 years profitable
    except Exception:
        return False


def calculate_multibagger_score(fundamentals: Dict) -> Dict[str, Any]:
    """
    Calculate multibagger score (0-100) based on fundamental quality.
    
    Scoring:
    - Growth (25 pts): Revenue CAGR, earnings growth
    - Profitability (25 pts): ROE, margins
    - Quality (20 pts): Low debt, FCF, consistency
    - Value (15 pts): PEG, PE discount
    - Moat (15 pts): Ownership, competitive position
    """
    scores = {
        "growth": {"score": 0, "max": 25, "details": []},
        "profitability": {"score": 0, "max": 25, "details": []},
        "quality": {"score": 0, "max": 20, "details": []},
        "value": {"score": 0, "max": 15, "details": []},
        "moat": {"score": 0, "max": 15, "details": []},
    }
    
    sector = fundamentals.get("sector", "Unknown")
    benchmarks = INDUSTRY_BENCHMARKS.get(sector, INDUSTRY_BENCHMARKS["Unknown"])
    
    # === GROWTH SCORE (25 pts) ===
    revenue_growth = fundamentals.get("revenue_growth")
    if revenue_growth is not None:
        if revenue_growth >= 25:
            scores["growth"]["score"] += 10
            scores["growth"]["details"].append(f"Excellent revenue growth: {revenue_growth}%")
        elif revenue_growth >= 15:
            scores["growth"]["score"] += 7
            scores["growth"]["details"].append(f"Strong revenue growth: {revenue_growth}%")
        elif revenue_growth >= 10:
            scores["growth"]["score"] += 5
            scores["growth"]["details"].append(f"Good revenue growth: {revenue_growth}%")
        elif revenue_growth >= 5:
            scores["growth"]["score"] += 3
            scores["growth"]["details"].append(f"Moderate growth: {revenue_growth}%")
    
    revenue_cagr = fundamentals.get("revenue_cagr_3y")
    if revenue_cagr is not None:
        if revenue_cagr >= 20:
            scores["growth"]["score"] += 8
            scores["growth"]["details"].append(f"Strong 3Y CAGR: {revenue_cagr}%")
        elif revenue_cagr >= 15:
            scores["growth"]["score"] += 6
        elif revenue_cagr >= 10:
            scores["growth"]["score"] += 4
    
    earnings_growth = fundamentals.get("earnings_growth")
    if earnings_growth is not None and earnings_growth > 0:
        if earnings_growth >= 20:
            scores["growth"]["score"] += 7
            scores["growth"]["details"].append(f"Strong EPS growth: {earnings_growth}%")
        elif earnings_growth >= 10:
            scores["growth"]["score"] += 5
    
    # === PROFITABILITY SCORE (25 pts) ===
    roe = fundamentals.get("roe")
    if roe is not None:
        if roe >= 20:
            scores["profitability"]["score"] += 12
            scores["profitability"]["details"].append(f"Excellent ROE: {roe}%")
        elif roe >= 15:
            scores["profitability"]["score"] += 9
            scores["profitability"]["details"].append(f"Good ROE: {roe}%")
        elif roe >= 12:
            scores["profitability"]["score"] += 6
    
    profit_margin = fundamentals.get("profit_margin")
    if profit_margin is not None:
        if profit_margin >= 15:
            scores["profitability"]["score"] += 8
            scores["profitability"]["details"].append(f"High margins: {profit_margin}%")
        elif profit_margin >= 10:
            scores["profitability"]["score"] += 6
        elif profit_margin >= 5:
            scores["profitability"]["score"] += 3
    
    operating_margin = fundamentals.get("operating_margin")
    if operating_margin is not None:
        if operating_margin >= 20:
            scores["profitability"]["score"] += 5
        elif operating_margin >= 12:
            scores["profitability"]["score"] += 3
    
    # === QUALITY SCORE (20 pts) ===
    de_ratio = fundamentals.get("debt_to_equity")
    if de_ratio is not None:
        if de_ratio <= 0.3:
            scores["quality"]["score"] += 8
            scores["quality"]["details"].append(f"Very low debt: D/E = {de_ratio}")
        elif de_ratio <= 0.5:
            scores["quality"]["score"] += 6
            scores["quality"]["details"].append(f"Low debt: D/E = {de_ratio}")
        elif de_ratio <= 1.0:
            scores["quality"]["score"] += 4
    else:
        scores["quality"]["score"] += 4  # No data = assume moderate
    
    if fundamentals.get("fcf_positive"):
        scores["quality"]["score"] += 6
        scores["quality"]["details"].append("Positive free cash flow")
    
    if fundamentals.get("earnings_consistent"):
        scores["quality"]["score"] += 6
        scores["quality"]["details"].append("Consistent earnings")
    
    # === VALUE SCORE (15 pts) ===
    peg = fundamentals.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg <= 1.0:
            scores["value"]["score"] += 8
            scores["value"]["details"].append(f"Attractive PEG: {peg}")
        elif peg <= 1.5:
            scores["value"]["score"] += 6
            scores["value"]["details"].append(f"Fair PEG: {peg}")
        elif peg <= 2.5:
            scores["value"]["score"] += 3
    
    pe = fundamentals.get("pe_ratio")
    if pe is not None:
        industry_pe = benchmarks["pe"]
        if pe < industry_pe * 0.7:
            scores["value"]["score"] += 7
            scores["value"]["details"].append(f"PE {pe} below industry avg {industry_pe}")
        elif pe < industry_pe:
            scores["value"]["score"] += 4
    
    # === MOAT SCORE (15 pts) ===
    insider = fundamentals.get("insider_holding")
    if insider is not None:
        if insider >= 60:
            scores["moat"]["score"] += 8
            scores["moat"]["details"].append(f"High promoter holding: {insider}%")
        elif insider >= 50:
            scores["moat"]["score"] += 6
            scores["moat"]["details"].append(f"Good promoter holding: {insider}%")
        elif insider >= 40:
            scores["moat"]["score"] += 4
    
    # Institutional holding indicates quality
    institutional = fundamentals.get("institutional_holding")
    if institutional is not None:
        if institutional >= 30:
            scores["moat"]["score"] += 5
            scores["moat"]["details"].append(f"Strong institutional interest: {institutional}%")
        elif institutional >= 20:
            scores["moat"]["score"] += 3
    
    # Known quality bonus
    if fundamentals.get("symbol") in KNOWN_QUALITY_STOCKS:
        scores["moat"]["score"] += 2
        scores["moat"]["details"].append("Established market leader")
    
    # Total score
    total_score = sum(s["score"] for s in scores.values())
    max_score = sum(s["max"] for s in scores.values())
    
    # Signal classification
    if total_score >= 75:
        signal = "STRONG BUY"
        recommendation = "Excellent multibagger candidate. Consider building position over 3-6 months."
    elif total_score >= 60:
        signal = "BUY"
        recommendation = "Quality growth stock. Good for long-term portfolio."
    elif total_score >= 45:
        signal = "HOLD/ACCUMULATE"
        recommendation = "Decent fundamentals. Accumulate on dips."
    elif total_score >= 30:
        signal = "WATCH"
        recommendation = "Mixed fundamentals. Monitor for improvement."
    else:
        signal = "AVOID"
        recommendation = "Weak fundamentals. Not recommended."
    
    return {
        "total_score": total_score,
        "max_score": max_score,
        "score_breakdown": scores,
        "signal": signal,
        "recommendation": recommendation
    }


def generate_investment_thesis(fundamentals: Dict, score_result: Dict) -> Dict[str, Any]:
    """Generate investment thesis with pros, cons, and target."""
    pros = []
    cons = []
    
    # Analyze key metrics
    roe = fundamentals.get("roe")
    if roe and roe >= 15:
        pros.append(f"High ROE of {roe}% indicates efficient capital usage")
    elif roe and roe < 10:
        cons.append(f"Low ROE of {roe}% suggests poor profitability")
    
    de_ratio = fundamentals.get("debt_to_equity")
    if de_ratio is not None:
        if de_ratio <= 0.5:
            pros.append(f"Conservative debt levels (D/E: {de_ratio})")
        elif de_ratio > 1.5:
            cons.append(f"High debt burden (D/E: {de_ratio})")
    
    revenue_growth = fundamentals.get("revenue_growth")
    if revenue_growth and revenue_growth >= 15:
        pros.append(f"Strong revenue growth of {revenue_growth}%")
    elif revenue_growth and revenue_growth < 5:
        cons.append(f"Slow revenue growth of {revenue_growth}%")
    
    if fundamentals.get("fcf_positive"):
        pros.append("Generates positive free cash flow")
    else:
        cons.append("Free cash flow concerns")
    
    peg = fundamentals.get("peg_ratio")
    if peg and peg <= 1.5:
        pros.append(f"Attractive valuation with PEG of {peg}")
    elif peg and peg > 3:
        cons.append(f"Expensive valuation with PEG of {peg}")
    
    insider = fundamentals.get("insider_holding")
    if insider and insider >= 50:
        pros.append(f"Strong promoter confidence ({insider}% holding)")
    
    # Calculate potential target (simple model)
    current_price = fundamentals.get("current_price", 0)
    pe = fundamentals.get("pe_ratio")
    earnings_growth = fundamentals.get("earnings_growth", 10)
    
    if current_price and pe and earnings_growth:
        # Simple 3-year projection
        projected_eps_growth = 1 + (min(earnings_growth, 25) / 100)  # Cap at 25%
        eps_multiplier = projected_eps_growth ** 3
        target_price = current_price * eps_multiplier
        upside = ((target_price - current_price) / current_price) * 100
    else:
        target_price = None
        upside = None
    
    return {
        "pros": pros[:5],  # Top 5 pros
        "cons": cons[:5],  # Top 5 cons
        "target_price_3y": round(target_price, 2) if target_price else None,
        "potential_upside": round(upside, 1) if upside else None,
        "time_horizon": "3-5 years",
        "suitable_for": "Long-term wealth creation, SIP investing"
    }


def run_multibagger_screener(
    symbols: List[str],
    top_n: int = 10,
    min_score: int = 50,
    min_market_cap: float = 1000  # Cr
) -> Dict:
    """
    Run the multibagger screener on given symbols.
    
    Parameters:
    - symbols: List of NSE symbols to screen
    - top_n: Number of top stocks to return
    - min_score: Minimum score (0-100) to qualify
    - min_market_cap: Minimum market cap in Crores
    
    Returns:
    - Dictionary with ranked candidates and analysis
    """
    results = {
        "screening_date": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "multibagger_investing",
        "version": "1.0",
        "stats": {
            "total_screened": len(symbols),
            "qualified": 0,
            "avg_score": 0
        },
        "candidates": [],
        "methodology": get_multibagger_methodology(),
        "status": "success"
    }
    
    # Fetch fundamentals in parallel
    candidates = []
    
    def process_symbol(symbol: str) -> Optional[Dict]:
        try:
            fundamentals = fetch_stock_fundamentals(symbol)
            
            if "error" in fundamentals:
                return None
            
            # Market cap filter (convert to Cr)
            market_cap_cr = (fundamentals.get("market_cap", 0) or 0) / 1e7
            if market_cap_cr < min_market_cap:
                return None
            
            # Calculate score
            score_result = calculate_multibagger_score(fundamentals)
            
            if score_result["total_score"] < min_score:
                return None
            
            # Generate thesis
            thesis = generate_investment_thesis(fundamentals, score_result)
            
            return {
                "symbol": symbol,
                "company_name": fundamentals.get("company_name", symbol),
                "sector": fundamentals.get("sector", "Unknown"),
                "current_price": fundamentals.get("current_price"),
                "market_cap_cr": round(market_cap_cr, 0),
                "score": score_result["total_score"],
                "signal": score_result["signal"],
                "recommendation": score_result["recommendation"],
                "score_breakdown": score_result["score_breakdown"],
                "key_metrics": {
                    "roe": fundamentals.get("roe"),
                    "revenue_growth": fundamentals.get("revenue_growth"),
                    "profit_margin": fundamentals.get("profit_margin"),
                    "debt_to_equity": fundamentals.get("debt_to_equity"),
                    "pe_ratio": fundamentals.get("pe_ratio"),
                    "peg_ratio": fundamentals.get("peg_ratio"),
                    "promoter_holding": fundamentals.get("insider_holding"),
                    "revenue_cagr_3y": fundamentals.get("revenue_cagr_3y"),
                },
                "investment_thesis": thesis,
                "from_52w_high": fundamentals.get("from_52w_high"),
                "dividend_yield": fundamentals.get("dividend_yield"),
            }
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            return None
    
    # Process symbols in parallel (max 5 concurrent)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_symbol, sym): sym for sym in symbols}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                candidates.append(result)
    
    # Sort by score and take top N
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:top_n]
    
    results["candidates"] = top_candidates
    results["stats"]["qualified"] = len(candidates)
    results["stats"]["avg_score"] = (
        sum(c["score"] for c in top_candidates) / len(top_candidates)
        if top_candidates else 0
    )
    results["message"] = f"Found {len(top_candidates)} multibagger candidates"
    
    # Sector distribution
    sector_counts = {}
    for c in top_candidates:
        sector = c.get("sector", "Unknown")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    results["sector_distribution"] = sector_counts
    
    return results


def get_multibagger_methodology() -> Dict:
    """Return methodology documentation."""
    return {
        "name": "Multibagger Screener",
        "objective": "Identify stocks with 2-10x return potential over 3-5 years",
        "scoring": {
            "growth": {
                "weight": 25,
                "criteria": "Revenue CAGR > 15%, EPS growth > 20%"
            },
            "profitability": {
                "weight": 25,
                "criteria": "ROE > 15%, Profit margin > 10%"
            },
            "quality": {
                "weight": 20,
                "criteria": "D/E < 0.5, Positive FCF, Consistent earnings"
            },
            "value": {
                "weight": 15,
                "criteria": "PEG < 1.5, PE below industry average"
            },
            "moat": {
                "weight": 15,
                "criteria": "Promoter > 50%, Institutional interest"
            }
        },
        "signals": {
            "STRONG BUY": "Score >= 75 - Excellent candidate",
            "BUY": "Score 60-74 - Quality growth stock",
            "HOLD": "Score 45-59 - Decent fundamentals",
            "WATCH": "Score 30-44 - Monitor for improvement",
            "AVOID": "Score < 30 - Weak fundamentals"
        },
        "investment_approach": {
            "time_horizon": "3-5 years minimum",
            "position_sizing": "Max 10% portfolio per stock",
            "entry_strategy": "SIP over 3-6 months",
            "review_frequency": "Quarterly fundamental review"
        },
        "risk_warnings": [
            "Past performance doesn't guarantee future returns",
            "Small/mid caps can be volatile",
            "Always diversify across 10-15 stocks minimum",
            "Fundamental data may be delayed"
        ]
    }


# Quick test function
def quick_screen_quality_stocks() -> List[str]:
    """Return a list of known quality stocks for quick screening."""
    return [
        "TCS", "INFY", "HDFCBANK", "ICICIBANK", "KOTAKBANK",
        "BAJFINANCE", "ASIANPAINT", "TITAN", "NESTLEIND", "HINDUNILVR",
        "RELIANCE", "MARUTI", "ULTRACEMCO", "BRITANNIA", "PIDILITIND",
        "HCLTECH", "WIPRO", "LT", "SUNPHARMA", "DRREDDY",
        "TATAMOTORS", "M&M", "EICHERMOT", "HAL", "BEL",
        "PERSISTENT", "COFORGE", "TATAELXSI", "DIVISLAB", "DMART"
    ]
