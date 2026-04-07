"""
BSE Chief Equity Analyst Report Generator

Synthesizes all available data — technicals, fundamentals, sector rotation,
news/events — into a single research-grade analyst report per stock.

Output per stock:
1. Executive Summary
2. Scorecard (0-10): Long-Term, Short-Term, Risk, Valuation, Quality
3. Classification: LONG-TERM / SHORT-TERM / AVOID
4. Long-term view (2-5 years)
5. Short-term view (1-12 weeks)
6. Bull / Base / Bear scenarios
7. Key catalysts & key risks
8. Trading / Investing plan with invalidation levels
9. Data quality notes & assumptions
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

SECTOR_INDICES_YAHOO = {
    "Banking": "^NSEBANK",
    "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG",
    "Auto": "^CNXAUTO",
    "Metal": "^CNXMETAL",
    "Metals": "^CNXMETAL",
    "Energy": "^CNXENERGY",
    "Realty": "^CNXREALTY",
    "Infrastructure": "^CNXINFRA",
    "Financial Services": "^CNXFIN",
    "PSU Bank": "^CNXPSUBANK",
    "Consumer Durables": "^CNXCONSUM",
    "Media": "^CNXMEDIA",
}

NIFTY_50_SYMBOL = "^NSEI"


def _fetch_index_data(yahoo_symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Fetch index data via yfinance."""
    try:
        import yfinance as yf
        df = yf.download(yahoo_symbol, period=period, progress=False)
        if df is not None and not df.empty:
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
            return df
    except Exception as e:
        logger.warning(f"Could not fetch index {yahoo_symbol}: {e}")
    return None


def calculate_sector_rotation_status(sector: str) -> Dict[str, Any]:
    """
    Compare sector index vs NIFTY 50 to identify rotation regime.

    Returns relative strength over 1M, 3M, 6M and a regime label.
    """
    result = {
        "sector": sector,
        "sector_index": None,
        "relative_strength_1m": None,
        "relative_strength_3m": None,
        "relative_strength_6m": None,
        "regime": "UNKNOWN",
        "data_available": False,
    }

    sector_yahoo = SECTOR_INDICES_YAHOO.get(sector)
    if not sector_yahoo:
        result["note"] = f"No sector index mapping for '{sector}'"
        return result

    nifty_df = _fetch_index_data(NIFTY_50_SYMBOL, "6mo")
    sector_df = _fetch_index_data(sector_yahoo, "6mo")

    if nifty_df is None or sector_df is None or nifty_df.empty or sector_df.empty:
        result["note"] = "Could not fetch index data"
        return result

    result["data_available"] = True
    result["sector_index"] = sector_yahoo

    def _pct_change(df, days):
        if len(df) < days:
            return None
        return float((df["close"].iloc[-1] / df["close"].iloc[-days] - 1) * 100)

    for label, days in [("1m", 22), ("3m", 66), ("6m", 132)]:
        s_ret = _pct_change(sector_df, days)
        n_ret = _pct_change(nifty_df, days)
        if s_ret is not None and n_ret is not None:
            result[f"relative_strength_{label}"] = round(s_ret - n_ret, 2)
            result[f"sector_return_{label}"] = round(s_ret, 2)
            result[f"nifty_return_{label}"] = round(n_ret, 2)

    rs_3m = result.get("relative_strength_3m")
    rs_1m = result.get("relative_strength_1m")

    if rs_3m is not None and rs_1m is not None:
        if rs_3m > 3 and rs_1m > 1:
            result["regime"] = "LEADING"
        elif rs_3m > 0 and rs_1m < -1:
            result["regime"] = "WEAKENING"
        elif rs_3m < -3 and rs_1m < -1:
            result["regime"] = "LAGGING"
        elif rs_3m < 0 and rs_1m > 1:
            result["regime"] = "IMPROVING"
        else:
            result["regime"] = "NEUTRAL"

    return result


def generate_chief_analyst_report(
    symbol: str,
    technical_df: Optional[pd.DataFrame] = None,
    sector: str = "Unknown",
) -> Dict[str, Any]:
    """
    Generate a complete BSE Chief Equity Analyst report for a single stock.

    Combines:
    - Yahoo Finance fundamentals + financials
    - Technical data from DB (if provided)
    - News signals
    - Sector rotation analysis

    Returns the full structured report.
    """
    report = {
        "symbol": symbol,
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analyst": "BSE Chief Equity Analyst (Algorithmic)",
        "data_sources_used": [],
        "data_quality_notes": [],
    }

    # ── 1. Fetch Fundamentals ──
    fundamentals = _fetch_fundamentals(symbol)
    if fundamentals.get("error"):
        report["error"] = fundamentals["error"]
        report["data_quality_notes"].append(
            f"Could not fetch fundamental data: {fundamentals['error']}"
        )
        fundamentals = {}
    else:
        report["data_sources_used"].append("Yahoo Finance (fundamentals, financials, ownership)")

    company_name = fundamentals.get("company_name", symbol)
    report["company_name"] = company_name
    report["sector"] = fundamentals.get("sector", sector)
    report["industry"] = fundamentals.get("industry", "Unknown")
    report["market_cap"] = fundamentals.get("market_cap")
    report["current_price"] = fundamentals.get("current_price")

    # ── 2. Technical Analysis (from DB data) ──
    tech = _analyze_technicals(technical_df, symbol)
    if tech.get("available"):
        report["data_sources_used"].append("NSE EOD data (technicals, indicators)")
    else:
        report["data_quality_notes"].append("Limited technical data from DB; using Yahoo price data as supplement")
    report["technicals"] = tech

    # ── 3. News & Events ──
    news_signals = _fetch_news_signals(symbol)
    report["news"] = news_signals
    if news_signals.get("items"):
        report["data_sources_used"].append("News (RSS, NSE Announcements, Yahoo Finance)")
    else:
        report["data_quality_notes"].append("No recent news found for this symbol")

    # ── 4. Sector Rotation ──
    sector_name = report["sector"]
    sector_rotation = calculate_sector_rotation_status(sector_name)
    report["sector_rotation"] = sector_rotation
    if sector_rotation.get("data_available"):
        report["data_sources_used"].append(f"Sector index ({sector_rotation.get('sector_index')} vs NIFTY 50)")

    # ── 5. Compute Scorecard (0-10 each) ──
    scorecard = _compute_scorecard(fundamentals, tech, news_signals, sector_rotation)
    report["scorecard"] = scorecard

    # ── 6. Classification ──
    classification = _classify_stock(scorecard, fundamentals, tech, news_signals)
    report["classification"] = classification

    # ── 7. Long-term & Short-term Views ──
    report["long_term_view"] = _generate_long_term_view(fundamentals, scorecard, sector_rotation)
    report["short_term_view"] = _generate_short_term_view(tech, news_signals, scorecard)

    # ── 8. Scenarios ──
    report["scenarios"] = _generate_scenarios(fundamentals, tech, scorecard)

    # ── 9. Key Catalysts & Risks ──
    catalysts, risks = _identify_catalysts_and_risks(fundamentals, tech, news_signals, sector_rotation)
    report["key_catalysts"] = catalysts
    report["key_risks"] = risks

    # ── 10. Trading / Investing Plan ──
    report["plan"] = _generate_plan(classification, tech, fundamentals, scorecard)

    # ── 11. Executive Summary (generated last, references everything) ──
    report["executive_summary"] = _generate_executive_summary(report)

    # ── 12. Data Checklist ──
    report["data_checklist"] = {
        "price_volume_data": tech.get("available", False),
        "quarterly_financials": bool(fundamentals.get("income_statement", {}).get("available")),
        "balance_sheet": bool(fundamentals.get("balance_sheet", {}).get("available")),
        "cash_flow": bool(fundamentals.get("cash_flow", {}).get("available")),
        "ownership_data": fundamentals.get("insider_holding") is not None,
        "news_events": len(news_signals.get("items", [])) > 0,
        "sector_index": sector_rotation.get("data_available", False),
        "earnings_quality": "earnings_quality" in fundamentals,
        "governance_score": "governance_score" in fundamentals,
    }

    report["fundamentals_snapshot"] = _extract_fundamentals_snapshot(fundamentals)

    return report


# ── Private helpers ──


def _fetch_fundamentals(symbol: str) -> Dict:
    """Fetch via financial_analysis module."""
    try:
        from app.financial_analysis import fetch_financial_data
        return fetch_financial_data(symbol)
    except Exception as e:
        logger.error(f"Fundamentals fetch failed for {symbol}: {e}")
        return {"error": str(e)}


def _fetch_news_signals(symbol: str) -> Dict:
    """Fetch news for a symbol."""
    try:
        from app.news_analyzer import get_news_aggregator
        agg = get_news_aggregator()
        signals = agg.get_signals_for_symbol(symbol)
        bull = sum(1 for s in signals if s.get("signal") in ["STRONG_BUY", "BUY"])
        bear = sum(1 for s in signals if s.get("signal") in ["STRONG_SELL", "SELL"])
        sentiment = "BULLISH" if bull > bear else "BEARISH" if bear > bull else "NEUTRAL"
        return {
            "items": signals[:15],
            "count": len(signals),
            "bullish_count": bull,
            "bearish_count": bear,
            "overall_sentiment": sentiment,
        }
    except Exception as e:
        logger.warning(f"News fetch failed for {symbol}: {e}")
        return {"items": [], "count": 0, "bullish_count": 0, "bearish_count": 0, "overall_sentiment": "UNKNOWN"}


def _analyze_technicals(df: Optional[pd.DataFrame], symbol: str) -> Dict:
    """Extract technical metrics from DB dataframe for a symbol."""
    result = {"available": False}
    if df is None or df.empty:
        return result

    sym_df = df[df["symbol"] == symbol] if "symbol" in df.columns else df
    if sym_df.empty:
        return result

    sym_df = sym_df.sort_values("trade_date") if "trade_date" in sym_df.columns else sym_df
    latest = sym_df.iloc[-1]
    result["available"] = True
    result["data_points"] = len(sym_df)

    close = float(latest.get("close", 0))
    sma20 = float(latest.get("sma_20", 0)) if pd.notna(latest.get("sma_20")) else None
    sma50 = float(latest.get("sma_50", 0)) if pd.notna(latest.get("sma_50")) else None
    rsi = float(latest.get("rsi_14", 50)) if pd.notna(latest.get("rsi_14")) else None
    atr = float(latest.get("atr_14", 0)) if pd.notna(latest.get("atr_14")) else None
    vol = float(latest.get("volume", 0))
    vol_ma = float(latest.get("vol_ma_20", 0)) if pd.notna(latest.get("vol_ma_20")) else None
    hh20 = float(latest.get("hh_20", 0)) if pd.notna(latest.get("hh_20")) else None
    ll20 = float(latest.get("ll_20", 0)) if pd.notna(latest.get("ll_20")) else None

    result["close"] = close
    result["sma_20"] = sma20
    result["sma_50"] = sma50
    result["rsi_14"] = rsi
    result["atr_14"] = atr
    result["atr_pct"] = round(atr / close * 100, 2) if atr and close else None
    result["volume"] = vol
    result["vol_ma_20"] = vol_ma
    result["vol_ratio"] = round(vol / vol_ma, 2) if vol_ma and vol_ma > 0 else None
    result["hh_20"] = hh20
    result["ll_20"] = ll20

    # Trend assessment
    trend_signals = []
    if sma20 and close > sma20:
        trend_signals.append("Above SMA20")
    if sma50 and close > sma50:
        trend_signals.append("Above SMA50")
    if sma20 and sma50 and sma20 > sma50:
        trend_signals.append("SMA20 > SMA50 (golden alignment)")

    if len(trend_signals) >= 3:
        result["trend"] = "STRONG_UPTREND"
    elif len(trend_signals) >= 2:
        result["trend"] = "UPTREND"
    elif len(trend_signals) >= 1:
        result["trend"] = "NEUTRAL"
    else:
        result["trend"] = "DOWNTREND"
    result["trend_signals"] = trend_signals

    # Momentum
    if rsi:
        if rsi >= 70:
            result["momentum"] = "OVERBOUGHT"
        elif rsi >= 55:
            result["momentum"] = "BULLISH"
        elif rsi >= 45:
            result["momentum"] = "NEUTRAL"
        elif rsi >= 30:
            result["momentum"] = "BEARISH"
        else:
            result["momentum"] = "OVERSOLD"

    # Breakout proximity
    if hh20 and close:
        dist = (hh20 - close) / hh20 * 100
        result["dist_from_20d_high_pct"] = round(dist, 2)
        result["near_breakout"] = dist < 2.0

    # Support / Resistance levels
    result["support_1"] = round(sma20, 2) if sma20 else None
    result["support_2"] = round(sma50, 2) if sma50 else None
    result["support_3"] = round(ll20, 2) if ll20 else None
    result["resistance_1"] = round(hh20, 2) if hh20 else None

    # Volatility
    if atr and close:
        atr_pct = atr / close * 100
        if atr_pct > 4:
            result["volatility"] = "HIGH"
        elif atr_pct > 2:
            result["volatility"] = "MODERATE"
        else:
            result["volatility"] = "LOW"

    # Max drawdown estimate (from 20d high)
    if hh20 and ll20:
        result["max_drawdown_20d"] = round((hh20 - ll20) / hh20 * 100, 2)

    return result


def _compute_scorecard(
    fundamentals: Dict, tech: Dict, news: Dict, sector_rot: Dict
) -> Dict[str, Any]:
    """Compute 0-10 scores for Long-Term, Short-Term, Risk, Valuation, Quality."""

    # Long-Term Score (fundamentals-driven)
    lt_score = 5.0
    roe = fundamentals.get("roe")
    if roe is not None:
        lt_score += min(2.0, roe / 10)
    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None and rev_growth > 0:
        lt_score += min(1.5, rev_growth / 15)
    if fundamentals.get("earnings_quality", {}).get("grade") in ["A", "B"]:
        lt_score += 1.0
    if fundamentals.get("governance_score", {}).get("grade") in ["A", "B"]:
        lt_score += 0.5
    lt_score = min(10, max(0, round(lt_score, 1)))

    # Short-Term Score (technicals + momentum + news)
    st_score = 5.0
    trend = tech.get("trend", "")
    if trend == "STRONG_UPTREND":
        st_score += 2.0
    elif trend == "UPTREND":
        st_score += 1.0
    elif trend == "DOWNTREND":
        st_score -= 2.0

    mom = tech.get("momentum", "")
    if mom == "BULLISH":
        st_score += 1.0
    elif mom == "OVERBOUGHT":
        st_score += 0.5
    elif mom in ["BEARISH", "OVERSOLD"]:
        st_score -= 1.5

    if tech.get("near_breakout"):
        st_score += 1.0
    vol_ratio = tech.get("vol_ratio")
    if vol_ratio and vol_ratio > 2:
        st_score += 1.0
    elif vol_ratio and vol_ratio > 1.5:
        st_score += 0.5

    news_sent = news.get("overall_sentiment", "")
    if news_sent == "BULLISH":
        st_score += 1.0
    elif news_sent == "BEARISH":
        st_score -= 1.0

    sr_regime = sector_rot.get("regime", "")
    if sr_regime == "LEADING":
        st_score += 0.5
    elif sr_regime == "LAGGING":
        st_score -= 0.5

    st_score = min(10, max(0, round(st_score, 1)))

    # Risk Score (lower = riskier; 10 = safest)
    risk_score = 6.0
    de = fundamentals.get("debt_to_equity")
    if de is not None:
        if de > 2:
            risk_score -= 3.0
        elif de > 1:
            risk_score -= 1.5
        elif de < 0.3:
            risk_score += 1.5
        elif de < 0.7:
            risk_score += 0.5

    vol_label = tech.get("volatility", "")
    if vol_label == "HIGH":
        risk_score -= 1.5
    elif vol_label == "LOW":
        risk_score += 1.0

    cr = fundamentals.get("current_ratio")
    if cr is not None:
        if cr < 1:
            risk_score -= 1.5
        elif cr >= 2:
            risk_score += 1.0

    gov_flags = fundamentals.get("governance_score", {}).get("red_flags", [])
    eq_flags = fundamentals.get("earnings_quality", {}).get("red_flags", [])
    risk_score -= len(gov_flags) * 0.5
    risk_score -= len(eq_flags) * 0.5

    beta = fundamentals.get("beta")
    if beta is not None and beta > 1.5:
        risk_score -= 0.5

    risk_score = min(10, max(0, round(risk_score, 1)))

    # Valuation Score
    val_score = 5.0
    pe = fundamentals.get("pe_ratio")
    if pe is not None:
        if pe < 10:
            val_score += 2.5
        elif pe < 20:
            val_score += 1.5
        elif pe < 30:
            val_score += 0.5
        elif pe > 60:
            val_score -= 2.0
        elif pe > 40:
            val_score -= 1.0

    peg = fundamentals.get("peg_ratio")
    if peg is not None:
        if peg < 1:
            val_score += 2.0
        elif peg < 1.5:
            val_score += 1.0
        elif peg > 3:
            val_score -= 1.5

    pb = fundamentals.get("pb_ratio")
    if pb is not None:
        if pb < 2:
            val_score += 0.5
        elif pb > 8:
            val_score -= 1.0

    val_score = min(10, max(0, round(val_score, 1)))

    # Quality Score
    qual_score = 5.0
    fin_score_pct = fundamentals.get("financial_score", {}).get("percentage", 0)
    qual_score += min(2.0, fin_score_pct / 25)

    eq_grade = fundamentals.get("earnings_quality", {}).get("grade", "N/A")
    if eq_grade == "A":
        qual_score += 2.0
    elif eq_grade == "B":
        qual_score += 1.0
    elif eq_grade == "D":
        qual_score -= 1.5

    gov_grade = fundamentals.get("governance_score", {}).get("grade", "N/A")
    if gov_grade == "A":
        qual_score += 1.0
    elif gov_grade == "D":
        qual_score -= 1.0

    qual_score = min(10, max(0, round(qual_score, 1)))

    return {
        "long_term": lt_score,
        "short_term": st_score,
        "risk": risk_score,
        "valuation": val_score,
        "quality": qual_score,
        "composite": round((lt_score + st_score + risk_score + val_score + qual_score) / 5, 1),
    }


def _classify_stock(
    scorecard: Dict, fundamentals: Dict, tech: Dict, news: Dict
) -> Dict[str, Any]:
    """Classify as LONG-TERM / SHORT-TERM / AVOID."""
    lt = scorecard["long_term"]
    st = scorecard["short_term"]
    risk = scorecard["risk"]
    quality = scorecard["quality"]
    val = scorecard["valuation"]

    red_flags = []
    red_flags.extend(fundamentals.get("governance_score", {}).get("red_flags", []))
    red_flags.extend(fundamentals.get("earnings_quality", {}).get("red_flags", []))

    # AVOID if dominant red flags
    if len(red_flags) >= 3 or risk < 3:
        tag = "AVOID"
        reasoning = "Multiple red flags dominate: " + "; ".join(red_flags[:3]) if red_flags else "Very high risk profile"
    elif quality < 3 and lt < 4:
        tag = "AVOID"
        reasoning = "Weak quality and poor long-term fundamentals"
    # LONG-TERM if quality + fundamentals + valuation align
    elif lt >= 6 and quality >= 6 and risk >= 5 and val >= 4.5:
        tag = "LONG-TERM"
        reasoning = "Quality fundamentals, reasonable valuation, acceptable risk — suitable for 2-5 year holding"
    elif lt >= 7 and quality >= 5:
        tag = "LONG-TERM"
        reasoning = "Strong growth profile with decent quality metrics"
    # SHORT-TERM if technicals + momentum + catalyst align
    elif st >= 6.5 and risk >= 4:
        tag = "SHORT-TERM"
        reasoning = "Strong technical setup with favorable momentum and sector alignment"
    elif st >= 5.5 and risk >= 5 and news.get("overall_sentiment") == "BULLISH":
        tag = "SHORT-TERM"
        reasoning = "Decent setup supported by positive news catalysts"
    # Borderline
    elif lt >= 5.5 and quality >= 5:
        tag = "LONG-TERM"
        reasoning = "Above-average fundamentals — accumulate on dips"
    elif st >= 5 and risk >= 4.5:
        tag = "SHORT-TERM"
        reasoning = "Moderate short-term setup; tight risk management required"
    else:
        tag = "AVOID"
        reasoning = "Neither long-term quality nor short-term momentum criteria met"

    return {
        "tag": tag,
        "reasoning": reasoning,
        "red_flags": red_flags,
    }


def _generate_long_term_view(
    fundamentals: Dict, scorecard: Dict, sector_rot: Dict
) -> Dict[str, Any]:
    """2-5 year outlook."""
    view = {"horizon": "2-5 years", "thesis": "", "key_factors": []}

    roe = fundamentals.get("roe")
    rev_growth = fundamentals.get("revenue_growth")
    de = fundamentals.get("debt_to_equity")
    pm = fundamentals.get("profit_margin")

    factors = []
    if roe and roe >= 15:
        factors.append(f"ROE of {roe}% indicates efficient capital deployment")
    if rev_growth and rev_growth >= 10:
        factors.append(f"Revenue growing at {rev_growth}% — above-average growth")
    if de is not None and de <= 0.5:
        factors.append(f"Conservative leverage (D/E: {de}) provides balance sheet cushion")
    if pm and pm >= 12:
        factors.append(f"Healthy profit margins at {pm}%")

    eq_grade = fundamentals.get("earnings_quality", {}).get("grade", "N/A")
    if eq_grade in ["A", "B"]:
        factors.append(f"Earnings quality grade {eq_grade} — sustainable profits")
    elif eq_grade == "D":
        factors.append("Earnings quality is poor — sustainability concern")

    sr = sector_rot.get("regime")
    if sr == "LEADING":
        factors.append("Sector is currently LEADING the market")
    elif sr == "LAGGING":
        factors.append("Sector is currently LAGGING — headwind for stock")

    view["key_factors"] = factors

    if scorecard["long_term"] >= 7:
        view["thesis"] = "Strong long-term candidate. Quality growth with sustainable earnings makes this suitable for multi-year compounding."
    elif scorecard["long_term"] >= 5:
        view["thesis"] = "Moderate long-term prospects. Some fundamental strengths but not a clear compounder. Accumulate selectively."
    else:
        view["thesis"] = "Weak long-term case. Fundamental gaps or valuation concerns suggest limited multi-year upside."

    return view


def _generate_short_term_view(
    tech: Dict, news: Dict, scorecard: Dict
) -> Dict[str, Any]:
    """1-12 week outlook."""
    view = {"horizon": "1-12 weeks", "thesis": "", "key_factors": []}

    factors = []
    trend = tech.get("trend", "UNKNOWN")
    factors.append(f"Trend: {trend}")

    mom = tech.get("momentum", "UNKNOWN")
    factors.append(f"Momentum: {mom} (RSI {tech.get('rsi_14', 'N/A')})")

    if tech.get("near_breakout"):
        factors.append("Price near 20-day breakout level")

    vr = tech.get("vol_ratio")
    if vr and vr > 1.5:
        factors.append(f"Volume {vr}x above average — institutional interest")

    sent = news.get("overall_sentiment", "UNKNOWN")
    factors.append(f"News sentiment: {sent}")

    view["key_factors"] = factors

    if scorecard["short_term"] >= 7:
        view["thesis"] = "Strong short-term setup. Trend, momentum, and catalysts align for a swing trade."
    elif scorecard["short_term"] >= 5:
        view["thesis"] = "Moderate short-term potential. Setup exists but conviction is not high — reduce position size."
    else:
        view["thesis"] = "Weak short-term setup. Technicals do not support near-term entry."

    return view


def _generate_scenarios(
    fundamentals: Dict, tech: Dict, scorecard: Dict
) -> Dict[str, Any]:
    """Bull / Base / Bear scenarios with price targets."""
    price = fundamentals.get("current_price", 0) or tech.get("close", 0)
    if not price:
        return {"bull": {}, "base": {}, "bear": {}, "note": "No price data"}

    pe = fundamentals.get("pe_ratio")
    eps = fundamentals.get("eps")
    atr = tech.get("atr_14", 0) or 0

    # Short-term targets (ATR-based)
    st_bull = round(price + atr * 3, 2) if atr else round(price * 1.08, 2)
    st_base = round(price + atr * 1.5, 2) if atr else round(price * 1.03, 2)
    st_bear = round(price - atr * 2, 2) if atr else round(price * 0.94, 2)

    # Long-term targets (earnings-based)
    if pe and eps and eps > 0:
        rev_g = fundamentals.get("revenue_growth", 10) or 10
        bull_growth = min(rev_g * 1.3, 30)
        base_growth = rev_g
        bear_growth = max(rev_g * 0.5, 0)

        lt_bull = round(price * (1 + bull_growth / 100) ** 3, 2)
        lt_base = round(price * (1 + base_growth / 100) ** 3, 2)
        lt_bear = round(price * (1 + bear_growth / 100) ** 3 * 0.85, 2)
    else:
        lt_bull = round(price * 1.50, 2)
        lt_base = round(price * 1.20, 2)
        lt_bear = round(price * 0.80, 2)

    return {
        "bull": {
            "label": "Bull Case",
            "probability": "25%",
            "short_term_target": st_bull,
            "long_term_target_3y": lt_bull,
            "description": "Earnings beat, sector tailwind, market rally",
        },
        "base": {
            "label": "Base Case",
            "probability": "50%",
            "short_term_target": st_base,
            "long_term_target_3y": lt_base,
            "description": "In-line growth, stable margins, no major surprise",
        },
        "bear": {
            "label": "Bear Case",
            "probability": "25%",
            "short_term_target": st_bear,
            "long_term_target_3y": lt_bear,
            "description": "Earnings miss, sector headwind, market correction",
        },
        "current_price": price,
    }


def _identify_catalysts_and_risks(
    fundamentals: Dict, tech: Dict, news: Dict, sector_rot: Dict
) -> tuple:
    """Return (catalysts, risks) lists."""
    catalysts = []
    risks = []

    # Fundamental catalysts
    rev_g = fundamentals.get("revenue_growth")
    if rev_g and rev_g >= 15:
        catalysts.append(f"Strong revenue growth ({rev_g}%) can drive re-rating")
    roe = fundamentals.get("roe")
    if roe and roe >= 18:
        catalysts.append(f"High ROE ({roe}%) attracts institutional interest")

    peg = fundamentals.get("peg_ratio")
    if peg and peg < 1:
        catalysts.append(f"PEG < 1 ({peg}) indicates undervaluation relative to growth")

    # Technical catalysts
    if tech.get("near_breakout"):
        catalysts.append("Near 20-day breakout — could trigger momentum buying")
    if tech.get("trend") == "STRONG_UPTREND":
        catalysts.append("Price in strong uptrend (above SMA20 & SMA50)")

    # News catalysts
    if news.get("overall_sentiment") == "BULLISH":
        catalysts.append(f"Positive news flow ({news.get('bullish_count', 0)} bullish signals)")
    for item in news.get("items", [])[:5]:
        if item.get("signal") in ["STRONG_BUY", "BUY"] and item.get("confidence", 0) > 60:
            catalysts.append(f"News: {item.get('headline', '')[:80]}")
            break

    # Sector
    if sector_rot.get("regime") == "LEADING":
        catalysts.append("Sector rotation favorable — sector outperforming market")

    # Risks
    de = fundamentals.get("debt_to_equity")
    if de and de > 1.5:
        risks.append(f"High leverage (D/E: {de}) — interest rate sensitivity")
    if tech.get("momentum") in ["OVERBOUGHT"]:
        risks.append("RSI overbought — near-term pullback likely")
    if tech.get("volatility") == "HIGH":
        risks.append("High volatility — wide stop-losses needed")
    if news.get("overall_sentiment") == "BEARISH":
        risks.append("Negative news flow could pressure stock")
    if sector_rot.get("regime") in ["LAGGING", "WEAKENING"]:
        risks.append("Sector headwind — sector underperforming market")

    for flag in fundamentals.get("governance_score", {}).get("red_flags", []):
        risks.append(f"Governance: {flag}")
    for flag in fundamentals.get("earnings_quality", {}).get("red_flags", []):
        risks.append(f"Earnings: {flag}")

    cr = fundamentals.get("current_ratio")
    if cr and cr < 1:
        risks.append(f"Liquidity concern (current ratio: {cr})")

    if not catalysts:
        catalysts.append("No strong catalysts identified — wait for better setup")
    if not risks:
        risks.append("Monitor for unexpected developments")

    return catalysts[:8], risks[:8]


def _generate_plan(
    classification: Dict, tech: Dict, fundamentals: Dict, scorecard: Dict
) -> Dict[str, Any]:
    """Generate actionable trading/investing plan with invalidation."""
    tag = classification["tag"]
    price = fundamentals.get("current_price", 0) or tech.get("close", 0)
    atr = tech.get("atr_14", 0) or 0

    if tag == "AVOID":
        return {
            "action": "NO ENTRY",
            "reasoning": classification["reasoning"],
            "invalidation": "Re-evaluate if red flags are resolved and scorecard improves above 6.0 composite",
        }

    plan = {"action": "", "entry_strategy": "", "exit_strategy": "",
            "stop_loss": None, "targets": [], "position_sizing": "",
            "invalidation": "", "time_horizon": ""}

    if tag == "LONG-TERM":
        plan["action"] = "ACCUMULATE"
        plan["time_horizon"] = "2-5 years"
        plan["entry_strategy"] = f"Build position over 3-6 months via SIP or dip-buying. Core entry zone: Rs {round(price * 0.95, 2)} - Rs {round(price * 1.02, 2)}"
        plan["stop_loss"] = round(price * 0.80, 2)
        plan["targets"] = [
            {"label": "Target 1 (1Y)", "price": round(price * 1.20, 2)},
            {"label": "Target 2 (3Y)", "price": round(price * 1.50, 2)},
            {"label": "Target 3 (5Y)", "price": round(price * 2.00, 2)},
        ]
        plan["position_sizing"] = "Max 10% of portfolio. Allocate in 3-4 tranches."
        plan["exit_strategy"] = "Review quarterly. Exit if ROE drops below 10% for 2 consecutive quarters, governance red flags emerge, or thesis breaks."
        plan["invalidation"] = "Thesis invalid if: (1) Revenue declines for 2 consecutive quarters, (2) D/E ratio exceeds 1.5, (3) Promoter holding drops below 25%, (4) Earnings quality grade drops to D"

    elif tag == "SHORT-TERM":
        sl = round(price - atr * 1.5, 2) if atr else round(price * 0.97, 2)
        plan["action"] = "SWING TRADE"
        plan["time_horizon"] = "1-4 weeks"
        plan["entry_strategy"] = f"Enter at Rs {round(price * 0.99, 2)} - Rs {round(price * 1.01, 2)} (within 1% of current)"
        plan["stop_loss"] = sl
        plan["targets"] = [
            {"label": "T1 (book 50%)", "price": round(price + atr * 1.5, 2) if atr else round(price * 1.03, 2)},
            {"label": "T2 (book 30%)", "price": round(price + atr * 2.5, 2) if atr else round(price * 1.05, 2)},
            {"label": "T3 (trail rest)", "price": round(price + atr * 4, 2) if atr else round(price * 1.08, 2)},
        ]
        plan["position_sizing"] = "Risk 2% of trading capital. Position size = (2% capital) / (entry - stop loss)"
        plan["exit_strategy"] = "Book 50% at T1. Trail stop to breakeven. Book 30% at T2. Let rest ride with trailing stop. Max hold: 5 trading days if no target hit."
        sl_pct = round((price - sl) / price * 100, 2)
        plan["invalidation"] = f"Exit immediately if: (1) Price closes below Rs {sl} (-{sl_pct}%), (2) Volume dries up (< 0.5x avg), (3) Broad market enters BEAR regime, (4) Adverse news breaks"

    return plan


def _generate_executive_summary(report: Dict) -> str:
    """Generate 2-3 sentence executive summary referencing key findings."""
    symbol = report["symbol"]
    company = report.get("company_name", symbol)
    tag = report.get("classification", {}).get("tag", "N/A")
    sc = report.get("scorecard", {})
    composite = sc.get("composite", 0)

    price = report.get("current_price") or report.get("technicals", {}).get("close", 0)
    sector = report.get("sector", "Unknown")

    summary = f"{company} ({symbol}) | Sector: {sector} | Classification: {tag} | Composite Score: {composite}/10."

    if tag == "LONG-TERM":
        lt_view = report.get("long_term_view", {}).get("thesis", "")
        summary += f" {lt_view}"
    elif tag == "SHORT-TERM":
        st_view = report.get("short_term_view", {}).get("thesis", "")
        summary += f" {st_view}"
    elif tag == "AVOID":
        reasoning = report.get("classification", {}).get("reasoning", "")
        summary += f" {reasoning}"

    # Add risk note
    risk = sc.get("risk", 5)
    if risk < 4:
        summary += " Risk is elevated — strict position sizing mandatory."
    elif risk >= 7:
        summary += " Risk profile is favorable."

    return summary


def _extract_fundamentals_snapshot(fundamentals: Dict) -> Dict:
    """Extract key fundamental metrics for display."""
    return {
        "pe_ratio": fundamentals.get("pe_ratio"),
        "pb_ratio": fundamentals.get("pb_ratio"),
        "peg_ratio": fundamentals.get("peg_ratio"),
        "ev_ebitda": fundamentals.get("ev_ebitda"),
        "roe": fundamentals.get("roe"),
        "roa": fundamentals.get("roa"),
        "profit_margin": fundamentals.get("profit_margin"),
        "operating_margin": fundamentals.get("operating_margin"),
        "debt_to_equity": fundamentals.get("debt_to_equity"),
        "current_ratio": fundamentals.get("current_ratio"),
        "revenue_growth": fundamentals.get("revenue_growth"),
        "earnings_growth": fundamentals.get("earnings_growth"),
        "dividend_yield": fundamentals.get("dividend_yield"),
        "insider_holding": fundamentals.get("insider_holding"),
        "institutional_holding": fundamentals.get("institutional_holding"),
        "beta": fundamentals.get("beta"),
        "52_week_high": fundamentals.get("52_week_high"),
        "52_week_low": fundamentals.get("52_week_low"),
        "market_cap": fundamentals.get("market_cap"),
        "financial_score": fundamentals.get("financial_score", {}).get("percentage"),
        "financial_rating": fundamentals.get("financial_score", {}).get("rating"),
        "earnings_quality_grade": fundamentals.get("earnings_quality", {}).get("grade"),
        "governance_grade": fundamentals.get("governance_score", {}).get("grade"),
    }


def generate_weekly_analyst_picks(
    df: pd.DataFrame,
    top_n: int = 2,
) -> Dict[str, Any]:
    """
    Generate the full weekly picks with Chief Analyst reports.
    Runs the elite screener first, then generates a full report for each pick.
    """
    from app.elite_screener import run_elite_screener

    if df.empty:
        return {"picks": [], "message": "No data available"}

    elite_result = run_elite_screener(
        df=df, top_n=top_n * 3, capital_per_trade=100000,
        min_score=60, min_price=100, sector_filter=True,
    )

    candidates = elite_result.get("candidates", [])
    if not candidates:
        return {"picks": [], "message": "No qualifying stocks this week", "market_regime": elite_result.get("market_regime")}

    picks_with_reports = []
    for candidate in candidates[:top_n]:
        symbol = candidate["symbol"]
        sector = candidate.get("sector", "Unknown")
        report = generate_chief_analyst_report(symbol, technical_df=df, sector=sector)
        report["elite_candidate"] = candidate
        picks_with_reports.append(report)

    return {
        "picks": picks_with_reports,
        "total_screened": elite_result.get("stats", {}).get("total_stocks", 0),
        "passed_filters": elite_result.get("stats", {}).get("passed_filters", 0),
        "market_regime": elite_result.get("market_regime"),
        "filters_applied": elite_result.get("filters_applied", []),
        "alternatives": [
            {"symbol": c["symbol"], "sector": c.get("sector"), "score": c["score"]}
            for c in candidates[top_n:top_n + 4]
        ],
    }
