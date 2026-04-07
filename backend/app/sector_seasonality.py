#!/usr/bin/env python3
"""
Sector Seasonality Analyzer
Analyzes 10 years of historical data to find:
1. Which sectors perform best in each month (heatmap)
2. Top stocks within sectors (undervalued + strong performers)
3. Financial metrics for recommendations
"""
import pandas as pd
import numpy as np
from typing import Optional
import yfinance as yf
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def calculate_monthly_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate monthly returns for each stock.
    Returns DataFrame with columns: symbol, sector, year, month, monthly_return
    """
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["year"] = df["trade_date"].dt.year
    df["month"] = df["trade_date"].dt.month

    # Get first and last close of each month for each stock
    monthly = df.groupby(["symbol", "sector", "year", "month"]).agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum"
    }).reset_index()

    # Calculate monthly return
    monthly["monthly_return"] = ((monthly["close"] - monthly["open"]) / monthly["open"]) * 100

    return monthly


def calculate_sector_seasonality(df: pd.DataFrame) -> dict:
    """
    Calculate sector seasonality heatmap data.
    Returns average monthly returns for each sector across 10 years.
    """
    monthly = calculate_monthly_returns(df)

    # Average monthly return by sector and month (across all years)
    sector_monthly = monthly.groupby(["sector", "month"]).agg({
        "monthly_return": ["mean", "std", "count"],
        "symbol": "nunique"
    }).reset_index()

    sector_monthly.columns = ["sector", "month", "avg_return", "std_return", "sample_count", "stock_count"]

    # Calculate win rate (% of positive months)
    monthly["positive"] = (monthly["monthly_return"] > 0).astype(int)
    win_rate = monthly.groupby(["sector", "month"])["positive"].mean().reset_index()
    win_rate.columns = ["sector", "month", "win_rate"]

    sector_monthly = sector_monthly.merge(win_rate, on=["sector", "month"])

    # Pivot for heatmap format
    heatmap_data = {}
    sectors = sector_monthly["sector"].unique()

    for sector in sectors:
        sector_data = sector_monthly[sector_monthly["sector"] == sector]
        monthly_stats = {}

        for _, row in sector_data.iterrows():
            month_num = int(row["month"])
            monthly_stats[MONTH_NAMES[month_num - 1]] = {
                "avg_return": round(row["avg_return"], 2),
                "std_return": round(row["std_return"], 2),
                "win_rate": round(row["win_rate"] * 100, 1),
                "sample_count": int(row["sample_count"]),
                "stock_count": int(row["stock_count"])
            }

        heatmap_data[sector] = monthly_stats

    return heatmap_data


def get_top_sectors_for_month(df: pd.DataFrame, month: int, top_n: int = 3) -> list:
    """
    Get top N sectors to invest in for a specific month.
    Ranks by: (1) average return, (2) win rate, (3) consistency (low std)
    """
    monthly = calculate_monthly_returns(df)

    # Filter for the target month
    month_data = monthly[monthly["month"] == month]

    # Aggregate by sector
    sector_stats = month_data.groupby("sector").agg({
        "monthly_return": ["mean", "std", "count"],
        "symbol": "nunique"
    }).reset_index()
    sector_stats.columns = ["sector", "avg_return", "std_return", "years_data", "stock_count"]

    # Calculate win rate
    month_data_copy = month_data.copy()
    month_data_copy["positive"] = (month_data_copy["monthly_return"] > 0).astype(int)
    win_rate = month_data_copy.groupby("sector")["positive"].mean().reset_index()
    win_rate.columns = ["sector", "win_rate"]

    sector_stats = sector_stats.merge(win_rate, on="sector")

    # Filter sectors with enough data (at least 5 years and 3 stocks)
    sector_stats = sector_stats[
        (sector_stats["years_data"] >= 30) &  # At least 30 data points (3 stocks * 10 years)
        (sector_stats["stock_count"] >= 3)
    ]

    # Calculate composite score
    # Higher avg return, higher win rate, lower std = better
    sector_stats["sharpe_like"] = sector_stats["avg_return"] / (sector_stats["std_return"] + 0.1)
    sector_stats["composite_score"] = (
        sector_stats["avg_return"] * 0.4 +
        sector_stats["win_rate"] * 100 * 0.3 +
        sector_stats["sharpe_like"] * 0.3
    )

    # Sort and get top N
    top_sectors = sector_stats.nlargest(top_n, "composite_score")

    result = []
    for _, row in top_sectors.iterrows():
        result.append({
            "sector": row["sector"],
            "avg_return": round(row["avg_return"], 2),
            "win_rate": round(row["win_rate"] * 100, 1),
            "std_return": round(row["std_return"], 2),
            "stock_count": int(row["stock_count"]),
            "years_analyzed": int(row["years_data"] / max(row["stock_count"], 1)),
            "composite_score": round(row["composite_score"], 2)
        })

    return result


def get_top_stocks_in_sector(df: pd.DataFrame, sector: str, top_n: int = 3) -> list:
    """
    Get top N stocks within a sector based on:
    1. Historical performance (10-year returns)
    2. Consistency (lower volatility)
    3. Current value (distance from 52-week high - undervalued)
    """
    sector_df = df[df["sector"] == sector].copy()

    if sector_df.empty:
        return []

    # Calculate stats per stock
    stock_stats = []

    for symbol in sector_df["symbol"].unique():
        stock_data = sector_df[sector_df["symbol"] == symbol].sort_values("trade_date")

        if len(stock_data) < 250:  # Need at least 1 year of data
            continue

        # Calculate metrics
        first_close = stock_data.iloc[0]["close"]
        last_close = stock_data.iloc[-1]["close"]
        total_return = ((last_close - first_close) / first_close) * 100

        # CAGR
        years = len(stock_data) / 250
        if years > 0 and first_close > 0:
            cagr = ((last_close / first_close) ** (1 / years) - 1) * 100
        else:
            cagr = 0

        # Volatility (annualized)
        daily_returns = stock_data["close"].pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100

        # 52-week high distance (undervalued indicator)
        high_52w = stock_data["high"].rolling(250).max().iloc[-1]
        current_price = last_close
        dist_from_high = ((high_52w - current_price) / high_52w) * 100

        # 52-week low distance
        low_52w = stock_data["low"].rolling(250).min().iloc[-1]
        dist_from_low = ((current_price - low_52w) / low_52w) * 100

        # Sharpe-like ratio
        sharpe = cagr / (volatility + 0.1) if volatility > 0 else 0

        # Win rate (% of positive months)
        monthly = calculate_monthly_returns(stock_data)
        win_rate = (monthly["monthly_return"] > 0).mean() * 100

        # Value score: stocks 10-30% below 52w high are considered undervalued
        # but not too far (could be losers)
        if 10 <= dist_from_high <= 40:
            value_score = 1.0
        elif dist_from_high < 10:
            value_score = 0.5  # Near high, less upside
        else:
            value_score = 0.3  # Too far from high, risky

        # Composite score
        composite = (
            cagr * 0.35 +
            sharpe * 10 * 0.25 +
            win_rate * 0.2 +
            value_score * 20 * 0.2
        )

        stock_stats.append({
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "total_return_10y": round(total_return, 2),
            "cagr": round(cagr, 2),
            "volatility": round(volatility, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate, 1),
            "dist_from_52w_high": round(dist_from_high, 2),
            "dist_from_52w_low": round(dist_from_low, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "is_undervalued": 10 <= dist_from_high <= 40,
            "composite_score": round(composite, 2)
        })

    # Sort by composite score
    stock_stats = sorted(stock_stats, key=lambda x: x["composite_score"], reverse=True)

    return stock_stats[:top_n]


def fetch_financial_data(symbol: str) -> dict:
    """
    Fetch financial data for a stock using yfinance.
    Returns PE, PB, dividend yield, market cap, etc.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info

        return {
            "symbol": symbol,
            "company_name": info.get("longName", symbol),
            "market_cap": info.get("marketCap", 0),
            "market_cap_cr": round(info.get("marketCap", 0) / 10000000, 2),  # In crores
            "pe_ratio": round(info.get("trailingPE", 0) or 0, 2),
            "forward_pe": round(info.get("forwardPE", 0) or 0, 2),
            "pb_ratio": round(info.get("priceToBook", 0) or 0, 2),
            "dividend_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
            "eps": round(info.get("trailingEps", 0) or 0, 2),
            "roe": round((info.get("returnOnEquity", 0) or 0) * 100, 2),
            "debt_to_equity": round(info.get("debtToEquity", 0) or 0, 2),
            "revenue_growth": round((info.get("revenueGrowth", 0) or 0) * 100, 2),
            "profit_margin": round((info.get("profitMargins", 0) or 0) * 100, 2),
            "52_week_high": round(info.get("fiftyTwoWeekHigh", 0) or 0, 2),
            "52_week_low": round(info.get("fiftyTwoWeekLow", 0) or 0, 2),
            "current_price": round(info.get("currentPrice", 0) or info.get("regularMarketPrice", 0) or 0, 2),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "book_value": round(info.get("bookValue", 0) or 0, 2),
            "recommendation": info.get("recommendationKey", "N/A")
        }
    except Exception as e:
        logger.error(f"Failed to fetch financial data for {symbol}: {e}")
        return {
            "symbol": symbol,
            "error": str(e)
        }


def get_sector_stocks_with_financials(df: pd.DataFrame, sector: str, top_n: int = 3) -> list:
    """
    Get top stocks in a sector with both historical performance and financial data.
    """
    top_stocks = get_top_stocks_in_sector(df, sector, top_n)

    for stock in top_stocks:
        financials = fetch_financial_data(stock["symbol"])
        stock["financials"] = financials

    return top_stocks


def get_current_month_recommendations(df: pd.DataFrame) -> dict:
    """
    Get recommendations for the current month.
    """
    current_month = datetime.now().month
    month_name = MONTH_NAMES[current_month - 1]

    top_sectors = get_top_sectors_for_month(df, current_month, top_n=3)

    recommendations = {
        "month": month_name,
        "month_number": current_month,
        "top_sectors": top_sectors,
        "sector_stocks": {}
    }

    # Get top stocks for each sector
    for sector_info in top_sectors:
        sector_name = sector_info["sector"]
        stocks = get_top_stocks_in_sector(df, sector_name, top_n=3)
        recommendations["sector_stocks"][sector_name] = stocks

    return recommendations


def validate_seasonality_stats(df: pd.DataFrame) -> dict:
    """
    Validate the seasonality statistics by running sanity checks.
    """
    monthly = calculate_monthly_returns(df)

    validation = {
        "total_records": len(df),
        "total_monthly_records": len(monthly),
        "unique_sectors": monthly["sector"].nunique(),
        "unique_stocks": monthly["symbol"].nunique(),
        "date_range": {
            "start": df["trade_date"].min(),
            "end": df["trade_date"].max()
        },
        "years_covered": monthly["year"].nunique(),
        "months_with_data": len(monthly.groupby(["year", "month"]).size()),
        "sector_coverage": {},
        "sanity_checks": []
    }

    # Check sector coverage
    for sector in monthly["sector"].unique():
        sector_data = monthly[monthly["sector"] == sector]
        validation["sector_coverage"][sector] = {
            "stock_count": sector_data["symbol"].nunique(),
            "total_months": len(sector_data),
            "years_with_data": sector_data["year"].nunique()
        }

    # Sanity checks
    # 1. Overall market return should be positive over 10 years
    overall_return = monthly["monthly_return"].mean()
    validation["sanity_checks"].append({
        "check": "Overall market monthly return is positive",
        "value": round(overall_return, 2),
        "passed": overall_return > 0
    })

    # 2. Returns should be realistic (-50% to +50% monthly is reasonable)
    extreme_returns = monthly[
        (monthly["monthly_return"] < -50) | (monthly["monthly_return"] > 50)
    ]
    validation["sanity_checks"].append({
        "check": "No extreme monthly returns (>50% or <-50%)",
        "value": len(extreme_returns),
        "passed": len(extreme_returns) < len(monthly) * 0.01  # Less than 1% extreme
    })

    # 3. Each month should have data
    months_covered = monthly.groupby("month").size()
    validation["sanity_checks"].append({
        "check": "All 12 months have data",
        "value": len(months_covered),
        "passed": len(months_covered) == 12
    })

    # 4. Standard deviation should be reasonable
    avg_std = monthly.groupby("sector")["monthly_return"].std().mean()
    validation["sanity_checks"].append({
        "check": "Average sector volatility is reasonable (5-20%)",
        "value": round(avg_std, 2),
        "passed": 5 <= avg_std <= 25
    })

    return validation
