"""
Comprehensive Sector Rotation Analysis

This module provides detailed sector analysis to help identify:
1. Which sectors are currently in favor (institutional buying)
2. Sector momentum and trend strength
3. Best stocks within each sector
4. Sector rotation signals (entering/leaving strength)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta


def convert_to_native(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_native(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_native(item) for item in obj]
    elif pd.isna(obj):
        return None
    return obj


# Sector definitions with sector ETF proxies (if available)
SECTOR_INFO = {
    "IT": {
        "name": "Information Technology",
        "description": "Software, IT services, digital transformation plays",
        "characteristics": "Growth-oriented, USD revenue exposure, high PE"
    },
    "Banking": {
        "name": "Banking & Financial Services",
        "description": "Private banks, PSU banks, NBFCs",
        "characteristics": "Interest rate sensitive, credit growth linked"
    },
    "Pharma": {
        "name": "Pharmaceuticals & Healthcare",
        "description": "Generic drugs, API, hospitals, diagnostics",
        "characteristics": "Defensive, USD revenue, regulatory sensitive"
    },
    "Auto": {
        "name": "Automobile & Auto Ancillaries",
        "description": "Passenger vehicles, commercial vehicles, EV plays",
        "characteristics": "Cyclical, rural demand linked, commodity sensitive"
    },
    "FMCG": {
        "name": "Fast Moving Consumer Goods",
        "description": "Consumer staples, packaged foods, personal care",
        "characteristics": "Defensive, rural demand, inflation pass-through"
    },
    "Metal": {
        "name": "Metals & Mining",
        "description": "Steel, aluminum, copper, mining companies",
        "characteristics": "Highly cyclical, global commodity prices linked"
    },
    "Energy": {
        "name": "Oil, Gas & Energy",
        "description": "Refineries, gas distribution, renewable energy",
        "characteristics": "Crude price sensitive, government policy linked"
    },
    "Infra": {
        "name": "Infrastructure & Construction",
        "description": "Roads, ports, construction, cement",
        "characteristics": "Capex cycle linked, order book driven"
    },
    "Realty": {
        "name": "Real Estate",
        "description": "Residential, commercial, REITs",
        "characteristics": "Interest rate sensitive, cyclical, region specific"
    },
    "Telecom": {
        "name": "Telecom & Media",
        "description": "Telecom operators, DTH, digital media",
        "characteristics": "Oligopolistic, ARPU improvement plays"
    },
    "Power": {
        "name": "Power & Utilities",
        "description": "Power generation, transmission, distribution",
        "characteristics": "Capital intensive, regulated returns"
    },
    "Chemicals": {
        "name": "Chemicals & Fertilizers",
        "description": "Specialty chemicals, agrochemicals, fertilizers",
        "characteristics": "China+1 beneficiary, crude derivative"
    },
    "Consumer": {
        "name": "Consumer Durables",
        "description": "Electronics, appliances, building materials",
        "characteristics": "Discretionary spending, housing cycle linked"
    },
    "Unknown": {
        "name": "Others",
        "description": "Miscellaneous sectors",
        "characteristics": "Varies by company"
    }
}


def calculate_sector_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate comprehensive metrics for each sector.
    """
    if df.empty or 'sector' not in df.columns:
        return pd.DataFrame()

    sector_metrics = []

    for sector in df['sector'].dropna().unique():
        if sector == '' or pd.isna(sector):
            continue

        sector_df = df[df['sector'] == sector].copy()

        if len(sector_df) < 2:
            continue

        # Basic counts
        total_stocks = len(sector_df)

        # Price metrics
        close_prices = sector_df['close'].dropna()

        # Trend metrics
        above_sma20 = 0
        above_sma50 = 0
        bullish_count = 0

        if 'sma_20' in sector_df.columns:
            above_sma20 = (sector_df['close'] > sector_df['sma_20']).sum()
        if 'sma_50' in sector_df.columns:
            above_sma50 = (sector_df['close'] > sector_df['sma_50']).sum()
            bullish_count = ((sector_df['close'] > sector_df['sma_20']) &
                           (sector_df['sma_20'] > sector_df['sma_50'])).sum()

        pct_above_sma20 = (above_sma20 / total_stocks) * 100 if total_stocks > 0 else 0
        pct_above_sma50 = (above_sma50 / total_stocks) * 100 if total_stocks > 0 else 0
        pct_bullish = (bullish_count / total_stocks) * 100 if total_stocks > 0 else 0

        # Momentum metrics
        avg_rsi = sector_df['rsi_14'].mean() if 'rsi_14' in sector_df.columns else 50
        avg_roc = sector_df['roc_10'].mean() if 'roc_10' in sector_df.columns else 0

        # Score metrics
        avg_score = sector_df['total_score'].mean() if 'total_score' in sector_df.columns else 10
        high_score_count = (sector_df['total_score'] >= 12).sum() if 'total_score' in sector_df.columns else 0

        # Relative strength
        avg_rs = sector_df['relative_strength'].mean() if 'relative_strength' in sector_df.columns else 1

        # Volume metrics
        avg_vol_ratio = sector_df['vol_ratio'].mean() if 'vol_ratio' in sector_df.columns else 1
        high_volume_count = (sector_df['vol_ratio'] >= 1.5).sum() if 'vol_ratio' in sector_df.columns else 0

        # ATR metrics
        avg_atr_pct = sector_df['atr_pct'].mean() if 'atr_pct' in sector_df.columns else 3

        # Composite sector score (0-100)
        sector_score = (
            pct_bullish * 0.25 +              # 25% weight on trend structure
            pct_above_sma50 * 0.20 +          # 20% weight on medium-term trend
            min(avg_rsi, 70) * 0.15 +         # 15% weight on momentum (capped)
            (avg_score / 20) * 100 * 0.20 +   # 20% weight on stock quality
            (avg_rs * 100 - 100) * 0.10 +     # 10% weight on relative strength
            min(avg_vol_ratio * 20, 30) * 0.10  # 10% weight on volume
        )

        # Determine sector phase
        if pct_bullish >= 60 and avg_rsi >= 55:
            phase = "LEADING"
            phase_description = "Strong momentum, institutional buying"
        elif pct_bullish >= 40 and avg_rsi >= 50:
            phase = "IMPROVING"
            phase_description = "Building strength, watch for breakouts"
        elif pct_bullish <= 30 and avg_rsi <= 45:
            phase = "LAGGING"
            phase_description = "Weak momentum, avoid for now"
        elif pct_bullish <= 40 and avg_rsi >= 50:
            phase = "WEAKENING"
            phase_description = "Losing momentum, take profits"
        else:
            phase = "NEUTRAL"
            phase_description = "Mixed signals, be selective"

        # Investment recommendation
        if sector_score >= 70 and phase in ["LEADING", "IMPROVING"]:
            recommendation = "OVERWEIGHT"
            rec_reason = "Strong technicals across the sector, increase allocation"
        elif sector_score >= 50 and phase not in ["LAGGING"]:
            recommendation = "NEUTRAL"
            rec_reason = "Mixed signals, maintain current allocation"
        else:
            recommendation = "UNDERWEIGHT"
            rec_reason = "Weak technicals, reduce exposure or avoid"

        sector_metrics.append({
            "sector": sector,
            "sector_info": SECTOR_INFO.get(sector, SECTOR_INFO["Unknown"]),
            "total_stocks": total_stocks,
            "sector_score": round(sector_score, 1),
            "phase": phase,
            "phase_description": phase_description,
            "recommendation": recommendation,
            "recommendation_reason": rec_reason,
            "metrics": {
                "pct_above_sma20": round(pct_above_sma20, 1),
                "pct_above_sma50": round(pct_above_sma50, 1),
                "pct_bullish_structure": round(pct_bullish, 1),
                "avg_rsi": round(avg_rsi, 1),
                "avg_momentum": round(avg_roc, 2),
                "avg_stock_score": round(avg_score, 1),
                "high_score_stocks": high_score_count,
                "avg_relative_strength": round(avg_rs, 3),
                "avg_volume_ratio": round(avg_vol_ratio, 2),
                "high_volume_stocks": high_volume_count,
                "avg_volatility": round(avg_atr_pct, 2)
            }
        })

    # Sort by sector score
    sector_metrics = sorted(sector_metrics, key=lambda x: x['sector_score'], reverse=True)

    return sector_metrics


def get_top_stocks_per_sector(df: pd.DataFrame, top_n: int = 3) -> Dict[str, List[Dict]]:
    """
    Get top N stocks for each sector based on score.
    """
    if df.empty or 'sector' not in df.columns:
        return {}

    result = {}

    for sector in df['sector'].dropna().unique():
        if sector == '' or pd.isna(sector):
            continue

        sector_df = df[df['sector'] == sector].copy()

        if 'total_score' in sector_df.columns:
            sector_df = sector_df.sort_values('total_score', ascending=False)
        elif 'score' in sector_df.columns:
            sector_df = sector_df.sort_values('score', ascending=False)

        top_stocks = []
        for _, row in sector_df.head(top_n).iterrows():
            stock_info = {
                "symbol": row.get('symbol', ''),
                "score": int(row.get('total_score', row.get('score', 0))),
                "close": float(row.get('close', 0)),
                "rsi": round(float(row.get('rsi_14', 50)), 1),
                "change_pct": round(float(row.get('roc_10', 0)), 2),
            }

            # Add strength indicator
            score = stock_info['score']
            if score >= 15:
                stock_info['strength'] = "STRONG"
            elif score >= 12:
                stock_info['strength'] = "MODERATE"
            else:
                stock_info['strength'] = "WEAK"

            top_stocks.append(stock_info)

        result[sector] = top_stocks

    return result


def analyze_sector_rotation(df: pd.DataFrame) -> Dict:
    """
    Comprehensive sector rotation analysis.

    Returns complete sector analysis with:
    - Sector rankings
    - Phase identification
    - Investment recommendations
    - Top stocks per sector
    """
    if df.empty:
        return {
            "error": "No data available",
            "sectors": [],
            "investment_summary": {}
        }

    # Calculate sector metrics
    sector_metrics = calculate_sector_metrics(df)

    # Get top stocks per sector
    top_stocks = get_top_stocks_per_sector(df, top_n=3)

    # Add top stocks to sector metrics
    for sector_data in sector_metrics:
        sector_data['top_stocks'] = top_stocks.get(sector_data['sector'], [])

    # Create investment summary
    leading_sectors = [s['sector'] for s in sector_metrics if s['phase'] == "LEADING"]
    improving_sectors = [s['sector'] for s in sector_metrics if s['phase'] == "IMPROVING"]
    lagging_sectors = [s['sector'] for s in sector_metrics if s['phase'] == "LAGGING"]
    overweight_sectors = [s['sector'] for s in sector_metrics if s['recommendation'] == "OVERWEIGHT"]

    # Best opportunities
    best_opportunities = []
    for sector_data in sector_metrics[:3]:  # Top 3 sectors
        for stock in sector_data.get('top_stocks', [])[:2]:  # Top 2 stocks per sector
            if stock.get('score', 0) >= 12:
                best_opportunities.append({
                    "symbol": stock['symbol'],
                    "sector": sector_data['sector'],
                    "score": stock['score'],
                    "reason": f"Top performer in {sector_data['phase'].lower()} sector"
                })

    result = {
        "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_sectors_analyzed": len(sector_metrics),
        "sectors": sector_metrics,
        "investment_summary": {
            "leading_sectors": leading_sectors,
            "improving_sectors": improving_sectors,
            "lagging_sectors": lagging_sectors,
            "overweight_recommendation": overweight_sectors,
            "sector_rotation_signal": get_rotation_signal(sector_metrics),
            "best_opportunities": best_opportunities[:5]
        },
        "strategy_recommendation": generate_strategy_recommendation(sector_metrics)
    }

    # Convert all numpy types to native Python types for JSON serialization
    return convert_to_native(result)


def get_rotation_signal(sector_metrics: List[Dict]) -> Dict:
    """
    Determine overall sector rotation signal.
    """
    if not sector_metrics:
        return {"signal": "NEUTRAL", "description": "Insufficient data"}

    leading_count = sum(1 for s in sector_metrics if s['phase'] == "LEADING")
    improving_count = sum(1 for s in sector_metrics if s['phase'] == "IMPROVING")
    lagging_count = sum(1 for s in sector_metrics if s['phase'] == "LAGGING")
    total = len(sector_metrics)

    # Check for broad market strength/weakness
    if leading_count >= total * 0.3:
        return {
            "signal": "RISK ON",
            "description": "Multiple sectors showing strength - favorable for equities",
            "action": "Increase equity allocation, focus on leading sectors"
        }
    elif improving_count >= total * 0.4:
        return {
            "signal": "IMPROVING",
            "description": "Sectors building momentum - early signs of rotation",
            "action": "Gradually increase exposure to improving sectors"
        }
    elif lagging_count >= total * 0.4:
        return {
            "signal": "RISK OFF",
            "description": "Multiple sectors showing weakness - defensive stance",
            "action": "Reduce equity exposure, focus on defensive sectors"
        }
    else:
        return {
            "signal": "SELECTIVE",
            "description": "Mixed sector performance - be selective",
            "action": "Focus only on leading sectors, avoid lagging ones"
        }


def generate_strategy_recommendation(sector_metrics: List[Dict]) -> Dict:
    """
    Generate overall strategy recommendation based on sector analysis.
    """
    if not sector_metrics:
        return {
            "strategy": "WAIT",
            "description": "Insufficient data for recommendation"
        }

    overweight_sectors = [s for s in sector_metrics if s['recommendation'] == "OVERWEIGHT"]
    leading_sectors = [s for s in sector_metrics if s['phase'] == "LEADING"]

    if len(overweight_sectors) >= 3:
        focus_sectors = [s['sector'] for s in overweight_sectors[:3]]
        return {
            "strategy": "AGGRESSIVE",
            "description": f"Strong momentum across multiple sectors. Focus on {', '.join(focus_sectors)}",
            "allocation": {
                sector: "25-30%" for sector in focus_sectors
            },
            "avoid": [s['sector'] for s in sector_metrics if s['phase'] == "LAGGING"]
        }
    elif len(leading_sectors) >= 2:
        focus_sectors = [s['sector'] for s in leading_sectors[:2]]
        return {
            "strategy": "MODERATE",
            "description": f"Selective strength in {', '.join(focus_sectors)}. Focus capital here.",
            "allocation": {
                sector: "30-40%" for sector in focus_sectors
            },
            "avoid": [s['sector'] for s in sector_metrics if s['phase'] == "LAGGING"]
        }
    elif len(overweight_sectors) >= 1:
        return {
            "strategy": "CONSERVATIVE",
            "description": f"Limited opportunities. Focus only on {overweight_sectors[0]['sector']}",
            "allocation": {
                overweight_sectors[0]['sector']: "50%",
                "Cash": "50%"
            },
            "avoid": [s['sector'] for s in sector_metrics if s['phase'] in ["LAGGING", "WEAKENING"]]
        }
    else:
        return {
            "strategy": "DEFENSIVE",
            "description": "No clear sector leadership. Stay defensive with high cash",
            "allocation": {
                "Cash": "60-70%",
                "Defensive (FMCG/Pharma)": "30-40%"
            },
            "avoid": [s['sector'] for s in sector_metrics if s['recommendation'] == "UNDERWEIGHT"]
        }
