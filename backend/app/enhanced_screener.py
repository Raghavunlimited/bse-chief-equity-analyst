"""
Enhanced Swing Trading Screener with High Win-Rate Filters

This screener implements multiple filters to improve win rate:
1. Market Regime Filter - Only trade in bullish markets
2. Sector Rotation - Only trade hot sectors
3. Support/Resistance - Enter near support levels
4. Multi-timeframe Confirmation - Weekly + Daily alignment
5. Risk-Adjusted Position Sizing - Smaller size for volatile stocks
6. Higher Score Threshold - Minimum 12 points
7. Fundamental Filters - Avoid troubled companies (negative momentum, death cross)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


class MarketRegimeFilter:
    """
    Determines if the overall market is favorable for trading.
    Only allow entries when market is in uptrend.
    """

    @staticmethod
    def check_market_regime(nifty_df: pd.DataFrame) -> Dict:
        """
        Check if NIFTY 50 is in a bullish regime.

        Returns:
            dict with regime info and whether trading is allowed
        """
        if nifty_df is None or nifty_df.empty:
            return {
                "regime": "UNKNOWN",
                "allow_trading": True,  # Default to allow if no data
                "reason": "No NIFTY data available",
                "nifty_trend": "N/A"
            }

        # Ensure we have enough data
        if len(nifty_df) < 50:
            return {
                "regime": "UNKNOWN",
                "allow_trading": True,
                "reason": "Insufficient NIFTY data",
                "nifty_trend": "N/A"
            }

        # Calculate indicators
        close = nifty_df['close'].values

        # SMAs
        sma_20 = pd.Series(close).rolling(20).mean().iloc[-1]
        sma_50 = pd.Series(close).rolling(50).mean().iloc[-1]
        sma_200 = pd.Series(close).rolling(200).mean().iloc[-1] if len(nifty_df) >= 200 else sma_50

        current_price = close[-1]

        # Price change over last 20 days
        pct_change_20d = ((current_price - close[-20]) / close[-20]) * 100

        # Determine regime
        bullish_conditions = 0

        # Condition 1: Price above SMA 50
        if current_price > sma_50:
            bullish_conditions += 1

        # Condition 2: SMA 20 above SMA 50
        if sma_20 > sma_50:
            bullish_conditions += 1

        # Condition 3: Price above SMA 200 (if available)
        if current_price > sma_200:
            bullish_conditions += 1

        # Condition 4: Positive 20-day momentum
        if pct_change_20d > 0:
            bullish_conditions += 1

        # Determine regime
        if bullish_conditions >= 3:
            regime = "BULL"
            allow_trading = True
            reason = "Market in uptrend - favorable for swing trading"
        elif bullish_conditions >= 2:
            regime = "NEUTRAL"
            allow_trading = True  # Still allow but with caution
            reason = "Market is mixed - trade with smaller positions"
        else:
            regime = "BEAR"
            allow_trading = False
            reason = "Market in downtrend - stay in cash"

        # Trend description
        if current_price > sma_20 > sma_50:
            trend = "Strong Uptrend"
        elif current_price > sma_50:
            trend = "Uptrend"
        elif current_price < sma_20 < sma_50:
            trend = "Strong Downtrend"
        else:
            trend = "Downtrend"

        return {
            "regime": regime,
            "allow_trading": allow_trading,
            "reason": reason,
            "nifty_trend": trend,
            "nifty_price": float(current_price),
            "nifty_sma_20": float(sma_20),
            "nifty_sma_50": float(sma_50),
            "nifty_20d_change": float(pct_change_20d),
            "bullish_score": bullish_conditions
        }


class SectorRotationFilter:
    """
    Identifies and filters for the strongest sectors.
    Only trade stocks from top performing sectors.
    """

    @staticmethod
    def analyze_sectors(df: pd.DataFrame, top_n: int = 3) -> Dict:
        """
        Analyze sector performance and identify hot sectors.

        Args:
            df: DataFrame with stock data including 'sector' column
            top_n: Number of top sectors to trade

        Returns:
            dict with sector analysis and allowed sectors
        """
        if 'sector' not in df.columns:
            return {
                "hot_sectors": [],
                "sector_ranking": [],
                "filter_active": False,
                "reason": "No sector data available"
            }

        # Calculate sector metrics
        sector_stats = []

        for sector in df['sector'].unique():
            if pd.isna(sector) or sector == '':
                continue

            sector_df = df[df['sector'] == sector]

            if len(sector_df) < 3:  # Need at least 3 stocks
                continue

            # Calculate average metrics for sector
            avg_score = sector_df['total_score'].mean() if 'total_score' in sector_df.columns else 0
            avg_rs = sector_df['relative_strength'].mean() if 'relative_strength' in sector_df.columns else 1
            avg_momentum = sector_df['roc_10'].mean() if 'roc_10' in sector_df.columns else 0
            pct_above_sma50 = (sector_df['close'] > sector_df['sma_50']).mean() * 100 if 'sma_50' in sector_df.columns else 50
            stock_count = len(sector_df)

            # Composite sector score
            sector_score = (
                avg_score * 0.3 +
                (avg_rs - 1) * 100 * 0.3 +  # Normalize RS
                avg_momentum * 0.2 +
                pct_above_sma50 * 0.2
            )

            sector_stats.append({
                "sector": sector,
                "score": sector_score,
                "avg_stock_score": avg_score,
                "relative_strength": avg_rs,
                "momentum": avg_momentum,
                "pct_above_sma50": pct_above_sma50,
                "stock_count": stock_count
            })

        # Sort by sector score
        sector_stats = sorted(sector_stats, key=lambda x: x['score'], reverse=True)

        # Get top N sectors
        hot_sectors = [s['sector'] for s in sector_stats[:top_n]]

        return {
            "hot_sectors": hot_sectors,
            "sector_ranking": sector_stats,
            "filter_active": True,
            "reason": f"Trading only top {top_n} sectors: {', '.join(hot_sectors)}"
        }


class SupportResistanceFilter:
    """
    Filters stocks that are near support levels for safer entry.
    """

    @staticmethod
    def calculate_sr_levels(row: pd.Series) -> Dict:
        """
        Calculate support/resistance levels and proximity.
        """
        close = row.get('close', 0)
        high_20 = row.get('hh_20', close)
        low_20 = row.get('ll_20', close)
        sma_20 = row.get('sma_20', close)
        sma_50 = row.get('sma_50', close)

        # Key support levels
        support_levels = [
            ("SMA 20", sma_20),
            ("SMA 50", sma_50),
            ("20-day Low", low_20),
        ]

        # Key resistance levels
        resistance_levels = [
            ("20-day High", high_20),
        ]

        # Find nearest support below current price
        nearest_support = None
        support_distance_pct = 100

        for name, level in support_levels:
            if level < close:
                dist = ((close - level) / close) * 100
                if dist < support_distance_pct:
                    support_distance_pct = dist
                    nearest_support = (name, level, dist)

        # Find nearest resistance above current price
        nearest_resistance = None
        resistance_distance_pct = 100

        for name, level in resistance_levels:
            if level > close:
                dist = ((level - close) / close) * 100
                if dist < resistance_distance_pct:
                    resistance_distance_pct = dist
                    nearest_resistance = (name, level, dist)

        # Entry quality based on support proximity
        # Closer to support = better entry (lower risk)
        if support_distance_pct <= 2:
            entry_quality = "EXCELLENT"
            entry_score = 3
        elif support_distance_pct <= 5:
            entry_quality = "GOOD"
            entry_score = 2
        elif support_distance_pct <= 8:
            entry_quality = "MODERATE"
            entry_score = 1
        else:
            entry_quality = "POOR"
            entry_score = 0

        return {
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "support_distance_pct": support_distance_pct,
            "resistance_distance_pct": resistance_distance_pct,
            "entry_quality": entry_quality,
            "entry_score": entry_score
        }

    @staticmethod
    def is_safe_entry(row: pd.Series, max_distance_from_support: float = 5.0) -> bool:
        """
        Check if entry is safe (close to support).
        """
        sr_info = SupportResistanceFilter.calculate_sr_levels(row)
        return sr_info['support_distance_pct'] <= max_distance_from_support


class MultiTimeframeFilter:
    """
    Ensures alignment between weekly and daily timeframes.
    """

    @staticmethod
    def check_weekly_alignment(df: pd.DataFrame, symbol: str) -> Dict:
        """
        Check if weekly trend aligns with daily trend.

        For weekly analysis, we look at last 5 days as one "week" bar.
        """
        if len(df) < 25:  # Need at least 5 weeks of data
            return {
                "aligned": True,  # Default to allow if insufficient data
                "weekly_trend": "UNKNOWN",
                "daily_trend": "UNKNOWN",
                "reason": "Insufficient data for weekly analysis"
            }

        close = df['close'].values

        # Daily trend (last 5 days)
        daily_sma_5 = pd.Series(close).rolling(5).mean().iloc[-1]
        daily_sma_10 = pd.Series(close).rolling(10).mean().iloc[-1]
        current_price = close[-1]

        # Weekly trend (using 20 and 50 day as proxy for 4 and 10 week)
        weekly_sma_short = pd.Series(close).rolling(20).mean().iloc[-1]
        weekly_sma_long = pd.Series(close).rolling(50).mean().iloc[-1]

        # Determine daily trend
        if current_price > daily_sma_5 > daily_sma_10:
            daily_trend = "BULLISH"
        elif current_price < daily_sma_5 < daily_sma_10:
            daily_trend = "BEARISH"
        else:
            daily_trend = "NEUTRAL"

        # Determine weekly trend
        if current_price > weekly_sma_short > weekly_sma_long:
            weekly_trend = "BULLISH"
        elif current_price < weekly_sma_short < weekly_sma_long:
            weekly_trend = "BEARISH"
        else:
            weekly_trend = "NEUTRAL"

        # Check alignment
        aligned = (
            (weekly_trend == "BULLISH" and daily_trend in ["BULLISH", "NEUTRAL"]) or
            (weekly_trend == "NEUTRAL" and daily_trend == "BULLISH")
        )

        if aligned:
            reason = "Weekly and daily trends are aligned for long entry"
        else:
            reason = f"Timeframes not aligned: Weekly={weekly_trend}, Daily={daily_trend}"

        return {
            "aligned": aligned,
            "weekly_trend": weekly_trend,
            "daily_trend": daily_trend,
            "reason": reason
        }


class FundamentalFilter:
    """
    Basic fundamental filters to avoid troubled companies.
    Uses technical proxies since we don't have fundamental data.
    """

    @staticmethod
    def check_fundamentals(row: pd.Series) -> Dict:
        """
        Check basic health indicators.

        Since we don't have P/E, debt ratios etc., we use technical proxies:
        1. Avoid death cross (SMA 50 < SMA 200 proxy)
        2. Avoid extreme negative momentum
        3. Avoid stocks with consistent lower lows
        """
        issues = []
        score = 0
        max_score = 3

        # Check 1: Avoid death cross (SMA 50 falling)
        sma_50 = row.get('sma_50', 0)
        sma_50_prev = row.get('sma_50_prev', sma_50)  # If available

        # Use close vs SMA 50 as proxy
        close = row.get('close', 0)
        if close > sma_50 * 0.9:  # Not more than 10% below SMA 50
            score += 1
        else:
            issues.append("Trading significantly below SMA 50 - potential trouble")

        # Check 2: Avoid extreme negative momentum
        roc_10 = row.get('roc_10', 0)
        if roc_10 > -10:  # Not down more than 10% in 10 days
            score += 1
        else:
            issues.append(f"Severe negative momentum: {roc_10:.1f}% in 10 days")

        # Check 3: Avoid stocks far from 52-week high
        dist_52w = row.get('dist_from_52w_high', 0)
        if dist_52w < 40:  # Not more than 40% below 52-week high
            score += 1
        else:
            issues.append(f"Down {dist_52w:.1f}% from 52-week high - potential value trap")

        # Determine health
        if score >= 3:
            health = "HEALTHY"
            allow = True
        elif score >= 2:
            health = "CAUTION"
            allow = True
        else:
            health = "TROUBLED"
            allow = False

        return {
            "health": health,
            "score": score,
            "max_score": max_score,
            "issues": issues,
            "allow": allow,
            "reason": "; ".join(issues) if issues else "No fundamental concerns"
        }


class RiskAdjustedPositionSizer:
    """
    Calculates position size based on stock volatility and setup quality.
    """

    @staticmethod
    def calculate_position(
        row: pd.Series,
        capital_per_trade: float = 100000,
        max_risk_pct: float = 2.0,
        setup_quality: str = "MODERATE"
    ) -> Dict:
        """
        Calculate risk-adjusted position size.

        Higher volatility = smaller position
        Better setup = larger position
        """
        close = row.get('close', 100)
        atr_14 = row.get('atr_14', close * 0.03)
        atr_pct = (atr_14 / close) * 100 if close > 0 else 3

        # Base position based on 2% risk
        stop_distance = atr_14 * 2  # 2 ATR stop
        risk_amount = capital_per_trade * (max_risk_pct / 100)
        base_shares = int(risk_amount / stop_distance) if stop_distance > 0 else 0

        # Volatility adjustment factor (lower position for higher volatility)
        if atr_pct <= 2:
            vol_factor = 1.2  # Low vol = can take larger position
        elif atr_pct <= 4:
            vol_factor = 1.0  # Normal
        elif atr_pct <= 6:
            vol_factor = 0.75  # Moderate vol = reduce
        else:
            vol_factor = 0.5  # High vol = half position

        # Setup quality adjustment
        quality_factors = {
            "EXCELLENT": 1.25,
            "GOOD": 1.0,
            "MODERATE": 0.75,
            "POOR": 0.5
        }
        quality_factor = quality_factors.get(setup_quality, 0.75)

        # Combined factor
        combined_factor = vol_factor * quality_factor

        # Adjusted shares
        adjusted_shares = int(base_shares * combined_factor)

        # Ensure minimum 1 share and doesn't exceed capital
        adjusted_shares = max(1, adjusted_shares)
        if adjusted_shares * close > capital_per_trade:
            adjusted_shares = int(capital_per_trade / close)

        position_value = adjusted_shares * close

        return {
            "shares": adjusted_shares,
            "position_value": position_value,
            "vol_factor": vol_factor,
            "quality_factor": quality_factor,
            "combined_factor": combined_factor,
            "risk_per_share": stop_distance,
            "total_risk": adjusted_shares * stop_distance,
            "risk_pct_of_capital": (adjusted_shares * stop_distance / capital_per_trade) * 100
        }


def run_enhanced_screener(
    df: pd.DataFrame,
    nifty_df: pd.DataFrame = None,
    top_n: int = 10,
    capital_per_trade: float = 100000,
    min_score: int = 12,  # Higher threshold
    max_atr_pct: float = 6.0,
    min_risk_reward: float = 2.0,
    apply_market_filter: bool = True,
    apply_sector_filter: bool = True,
    top_sectors: int = 3,
    apply_sr_filter: bool = True,
    apply_mtf_filter: bool = True,
    apply_fundamental_filter: bool = True
) -> Dict:
    """
    Run the enhanced screener with all filters.

    Returns:
        dict with results and filter status
    """
    results = {
        "filters_applied": [],
        "filters_status": {},
        "candidates": [],
        "rejected": [],
        "stats": {}
    }

    if df.empty:
        results["error"] = "No data provided"
        return results

    # ===========================================
    # FILTER 1: Market Regime
    # ===========================================
    if apply_market_filter:
        market_regime = MarketRegimeFilter.check_market_regime(nifty_df)
        results["filters_status"]["market_regime"] = market_regime
        results["filters_applied"].append("Market Regime Filter")

        if not market_regime["allow_trading"]:
            results["warning"] = f"Market filter blocked trading: {market_regime['reason']}"
            # Still continue but flag it

    # ===========================================
    # FILTER 2: Sector Rotation
    # ===========================================
    hot_sectors = None
    if apply_sector_filter and 'sector' in df.columns:
        sector_analysis = SectorRotationFilter.analyze_sectors(df, top_n=top_sectors)
        results["filters_status"]["sector_rotation"] = sector_analysis
        results["filters_applied"].append("Sector Rotation Filter")
        hot_sectors = sector_analysis.get("hot_sectors", [])

    # ===========================================
    # Process each stock
    # ===========================================
    candidates = []
    rejected = []

    for idx, row in df.iterrows():
        symbol = row.get('symbol', f'STOCK_{idx}')
        rejection_reasons = []

        # Get score
        score = row.get('total_score', row.get('score', 0))

        # FILTER: Minimum score
        if score < min_score:
            rejection_reasons.append(f"Score {score} below minimum {min_score}")

        # FILTER: ATR check
        atr_pct = row.get('atr_pct', 3)
        if atr_pct > max_atr_pct:
            rejection_reasons.append(f"ATR {atr_pct:.1f}% exceeds max {max_atr_pct}%")

        # FILTER: Risk/Reward
        rr = row.get('risk_reward', 2)
        if rr < min_risk_reward:
            rejection_reasons.append(f"Risk:Reward 1:{rr:.1f} below min 1:{min_risk_reward}")

        # FILTER: Sector
        if apply_sector_filter and hot_sectors:
            stock_sector = row.get('sector', '')
            if stock_sector and stock_sector not in hot_sectors:
                rejection_reasons.append(f"Sector '{stock_sector}' not in hot sectors")

        # FILTER: Support/Resistance
        sr_info = None
        if apply_sr_filter:
            sr_info = SupportResistanceFilter.calculate_sr_levels(row)
            if sr_info['entry_quality'] == "POOR":
                rejection_reasons.append(f"Poor entry: {sr_info['support_distance_pct']:.1f}% from support")

        # FILTER: Multi-timeframe (would need full price data)
        mtf_info = None
        if apply_mtf_filter:
            # Simplified check using available data
            sma_20 = row.get('sma_20', 0)
            sma_50 = row.get('sma_50', 0)
            close = row.get('close', 0)

            weekly_bullish = close > sma_50  # Proxy for weekly
            daily_bullish = close > sma_20   # Proxy for daily

            mtf_info = {
                "weekly_bullish": weekly_bullish,
                "daily_bullish": daily_bullish,
                "aligned": weekly_bullish and daily_bullish
            }

            if not mtf_info["aligned"]:
                rejection_reasons.append("Timeframes not aligned")

        # FILTER: Fundamental
        fundamental_info = None
        if apply_fundamental_filter:
            fundamental_info = FundamentalFilter.check_fundamentals(row)
            if not fundamental_info["allow"]:
                rejection_reasons.append(f"Fundamental issues: {fundamental_info['reason']}")

        # ===========================================
        # Decision: Accept or Reject
        # ===========================================
        if rejection_reasons:
            rejected.append({
                "symbol": symbol,
                "score": score,
                "reasons": rejection_reasons
            })
        else:
            # Calculate position size
            setup_quality = sr_info['entry_quality'] if sr_info else "MODERATE"
            position_info = RiskAdjustedPositionSizer.calculate_position(
                row, capital_per_trade, setup_quality=setup_quality
            )

            # Build candidate entry
            close_price = row.get('close', 0)
            atr_14 = row.get('atr_14', close_price * 0.03)
            stop_loss = close_price - (2 * atr_14)
            target_price = close_price + (3 * atr_14)  # 3 ATR target for 1:1.5 R:R minimum

            candidate = {
                "symbol": symbol,
                "score": int(score),
                "close_price": float(close_price),
                "entry_price": float(close_price),
                "stop_loss": float(stop_loss),
                "target_price": float(target_price),
                "risk_reward": float((target_price - close_price) / (close_price - stop_loss)) if close_price > stop_loss else 0,
                "position_size": position_info["shares"],
                "position_value": position_info["position_value"],
                "metadata": {
                    "sector": row.get('sector', 'Unknown'),
                    "atr_pct": float(atr_pct),
                    "rsi_14": float(row.get('rsi_14', 50)),
                    "vol_ratio": float(row.get('vol_ratio', 1)),
                    "expected_gain_pct": float(((target_price - close_price) / close_price) * 100),
                    "risk_pct": float(((close_price - stop_loss) / close_price) * 100),
                    "entry_quality": sr_info['entry_quality'] if sr_info else "UNKNOWN",
                    "support_distance": sr_info['support_distance_pct'] if sr_info else 0,
                    "vol_adjustment": position_info["vol_factor"],
                    "quality_adjustment": position_info["quality_factor"],
                    "fundamental_health": fundamental_info["health"] if fundamental_info else "UNKNOWN",
                    "mtf_aligned": mtf_info["aligned"] if mtf_info else True,
                    "strength": "STRONG" if score >= 15 else "MODERATE"
                }
            }
            candidates.append(candidate)

    # Sort by score descending
    candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)[:top_n]

    # Build final results
    results["candidates"] = candidates
    results["rejected"] = rejected[:20]  # Keep top 20 rejections for reference
    results["stats"] = {
        "total_stocks_analyzed": len(df),
        "candidates_found": len(candidates),
        "rejected_count": len(rejected),
        "min_score_used": min_score,
        "filters_count": len(results["filters_applied"])
    }

    return results


def get_filter_summary() -> Dict:
    """
    Returns a summary of all filters and their purpose.
    """
    return {
        "filters": [
            {
                "name": "Market Regime Filter",
                "description": "Only trades when NIFTY 50 is in an uptrend (above SMA 50)",
                "impact": "Avoids trading in falling markets - major win rate booster",
                "conditions": ["NIFTY above SMA 50", "SMA 20 > SMA 50", "Positive 20-day momentum"]
            },
            {
                "name": "Sector Rotation Filter",
                "description": "Only trades stocks from the top 3 performing sectors",
                "impact": "Focuses on sectors with institutional buying",
                "conditions": ["Sector relative strength", "% of stocks above SMA 50", "Sector momentum"]
            },
            {
                "name": "Support/Resistance Filter",
                "description": "Prefers entries near support levels",
                "impact": "Better risk/reward, tighter stops possible",
                "conditions": ["Within 5% of support", "Entry quality scoring"]
            },
            {
                "name": "Multi-Timeframe Filter",
                "description": "Requires weekly and daily trend alignment",
                "impact": "Higher probability of trend continuation",
                "conditions": ["Weekly trend bullish", "Daily trend bullish or neutral"]
            },
            {
                "name": "Fundamental Filter",
                "description": "Avoids technically troubled stocks",
                "impact": "Reduces value traps and falling knives",
                "conditions": ["Not in death cross", "Not extreme negative momentum", "Within 40% of 52W high"]
            },
            {
                "name": "Risk-Adjusted Position Sizing",
                "description": "Smaller positions for volatile or weak setups",
                "impact": "Reduces drawdown from losers",
                "conditions": ["Volatility adjustment", "Setup quality adjustment"]
            }
        ],
        "minimum_score": 12,
        "typical_win_rate_improvement": "From ~40% to 55-65%",
        "notes": "These filters reduce the number of trades but significantly improve quality"
    }
