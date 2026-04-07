from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from functools import lru_cache
import logging
import pandas as pd
import numpy as np
import json
import time

from app.config import config
from app.store import Database
from app.ingest import NSEDataIngester
from app.features import compute_indicators_for_all_symbols, extract_indicator_columns, get_latest_snapshot_per_symbol
from app.screener import run_screener
from app.backtest import Backtest
from app.analysis import generate_pros_cons, get_score_explanation, generate_recommendation, calculate_support_resistance
from app.enhanced_screener import (
    run_enhanced_screener,
    get_filter_summary,
    MarketRegimeFilter,
    SectorRotationFilter,
    SupportResistanceFilter,
    FundamentalFilter,
    RiskAdjustedPositionSizer
)
from app.advanced_screener import add_advanced_indicators, score_for_swing_trade
from app.sector_analysis import analyze_sector_rotation, calculate_sector_metrics, get_top_stocks_per_sector, SECTOR_INFO, convert_to_native
from app.pattern_recognition import calculate_pattern_score, calculate_trend_strength, get_pattern_summary
from app.ultimate_screener import run_ultimate_screener, calculate_ultimate_score, get_screener_summary
from app.elite_screener import run_elite_screener, get_methodology as get_elite_methodology
from app.sector_seasonality import (
    calculate_sector_seasonality,
    get_top_sectors_for_month,
    get_top_stocks_in_sector,
    get_sector_stocks_with_financials,
    get_current_month_recommendations,
    validate_seasonality_stats,
    MONTH_NAMES
)
from app.news_analyzer import get_news_aggregator, NewsAggregator
from app.financial_analysis import fetch_financial_data
from app.chief_analyst import (
    generate_chief_analyst_report,
    generate_weekly_analyst_picks,
    calculate_sector_rotation_status,
)
from app.multibagger_screener import (
    run_multibagger_screener, 
    get_multibagger_methodology,
    quick_screen_quality_stocks,
    fetch_stock_fundamentals,
    calculate_multibagger_score
)
from nse_stocks import SECTOR_MAP, FUTURISTIC_SECTORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ============================================================================
# CACHING LAYER - Improves performance for frequently accessed data
# ============================================================================
class SimpleCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self._cache: Dict[str, tuple] = {}  # {key: (value, expiry_time)}
        self.default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                self._stats["hits"] += 1
                return value
            else:
                del self._cache[key]
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        ttl = ttl or self.default_ttl
        self._cache[key] = (value, time.time() + ttl)
    
    def clear(self):
        self._cache.clear()
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching a pattern."""
        keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        for k in keys_to_delete:
            del self._cache[k]
    
    @property
    def stats(self):
        return self._stats

# Initialize cache
cache = SimpleCache(default_ttl=300)  # 5 minute default TTL

# Initialize FastAPI app
app = FastAPI(
    title="NSE Weekly Swing Trader",
    description="Advanced screener for weekly swing trading opportunities in NSE stocks",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = Database(config.db_path)


# Pydantic models
class ScreenerResult(BaseModel):
    symbol: str
    score: float
    close_price: float
    entry_price: float
    stop_loss: float
    target_price: float
    risk_reward: float
    position_size: int
    metadata: dict


class IngestionStatus(BaseModel):
    status: str
    message: str
    records_processed: Optional[int] = None
    date: Optional[str] = None


class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    capital: float = 1000000
    max_positions: int = 10


class BacktestResult(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_return: float
    median_return: float
    best_trade: float
    worst_trade: float
    profit_factor: float
    target_hit_rate: float
    stop_hit_rate: float


class DateRangeRequest(BaseModel):
    start_date: str
    end_date: str


# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": "NSE Weekly Swing Trader",
        "version": "2.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": "NSE Weekly Swing Trader",
        "version": "2.0.0"
    }


@app.get("/api/screener/latest")
async def get_latest_screener_results(limit: int = 25):
    """Get latest screener results"""
    try:
        results_df = db.get_latest_screener_results(limit=limit)

        if results_df.empty:
            return []

        results = []
        for _, row in results_df.iterrows():
            result = {
                "symbol": row["symbol"],
                "score": row["score"],
                "close_price": row["close_price"],
                "entry_price": row["entry_price"],
                "stop_loss": row["stop_loss"],
                "target_price": row["target_price"],
                "risk_reward": row["risk_reward"],
                "position_size": row["position_size"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            }
            results.append(result)

        return results

    except Exception as e:
        logger.error(f"Error fetching screener results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/by-date")
async def get_screener_by_date(date: str, limit: int = 25):
    """Get screener results for a specific date"""
    try:
        query = """
        SELECT * FROM screener_results
        WHERE screening_date = ?
        ORDER BY score DESC
        LIMIT ?
        """
        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=(date, limit))

        if df.empty:
            return {"date": date, "results": [], "message": "No results for this date"}

        results = []
        for _, row in df.iterrows():
            results.append({
                "symbol": row["symbol"],
                "score": row["score"],
                "close_price": row["close_price"],
                "entry_price": row["entry_price"],
                "stop_loss": row["stop_loss"],
                "target_price": row["target_price"],
                "risk_reward": row["risk_reward"],
                "position_size": row["position_size"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            })

        return {"date": date, "results": results}

    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}")
async def get_stock_details(symbol: str):
    """Get detailed analysis for a specific stock"""
    try:
        # Get price history
        query = """
        SELECT e.*, i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
        FROM eod e
        LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.symbol = ?
        ORDER BY e.trade_date DESC
        LIMIT 100
        """
        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=(symbol,))

        if df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        df = df.sort_values("trade_date")
        latest = df.iloc[-1]

        # Calculate additional metrics
        df["vol_ma_20"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_ma_20"]
        df["daily_return"] = df["close"].pct_change() * 100

        # Support/Resistance
        sr_levels = calculate_support_resistance(df)

        # Pros and Cons
        latest_with_extras = latest.copy()
        latest_with_extras["vol_ratio"] = df["vol_ratio"].iloc[-1] if "vol_ratio" in df else 1
        latest_with_extras["atr_pct"] = (latest.get("atr_14", 0) / latest["close"]) * 100 if latest["close"] > 0 else 0
        latest_with_extras["dist_from_20d_high"] = ((df["high"].tail(20).max() - latest["close"]) / df["high"].tail(20).max()) * 100
        latest_with_extras["dist_from_52w_high"] = ((df["high"].max() - latest["close"]) / df["high"].max()) * 100

        pros_cons = generate_pros_cons(latest_with_extras)
        recommendation = generate_recommendation(latest_with_extras)

        # Prepare chart data
        chart_data = []
        for _, row in df.iterrows():
            chart_data.append({
                "date": row["trade_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "sma_20": float(row["sma_20"]) if pd.notna(row.get("sma_20")) else None,
                "sma_50": float(row["sma_50"]) if pd.notna(row.get("sma_50")) else None
            })

        return {
            "symbol": symbol,
            "current_price": float(latest["close"]),
            "change_pct": float(df["daily_return"].iloc[-1]) if len(df) > 1 else 0,
            "volume": int(latest["volume"]),
            "indicators": {
                "rsi_14": float(latest.get("rsi_14", 0)) if pd.notna(latest.get("rsi_14")) else None,
                "sma_20": float(latest.get("sma_20", 0)) if pd.notna(latest.get("sma_20")) else None,
                "sma_50": float(latest.get("sma_50", 0)) if pd.notna(latest.get("sma_50")) else None,
                "atr_14": float(latest.get("atr_14", 0)) if pd.notna(latest.get("atr_14")) else None,
                "atr_pct": float(latest_with_extras.get("atr_pct", 0)),
                "vol_ratio": float(latest_with_extras.get("vol_ratio", 1))
            },
            "support_resistance": sr_levels,
            "pros_cons": pros_cons,
            "recommendation": recommendation,
            "chart_data": chart_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stock details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    period: str = Query("3M", description="Period: 1W, 1M, 3M, 6M, 1Y")
):
    """Get OHLCV chart data for a stock"""
    try:
        # Determine date range
        days_map = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}
        days = days_map.get(period, 90)

        query = """
        SELECT e.trade_date, e.open, e.high, e.low, e.close, e.volume,
               i.sma_20, i.sma_50
        FROM eod e
        LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.symbol = ?
        ORDER BY e.trade_date DESC
        LIMIT ?
        """
        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=(symbol, days))

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        df = df.sort_values("trade_date")

        # Format for candlestick chart
        candles = []
        volumes = []

        for _, row in df.iterrows():
            is_bullish = row["close"] >= row["open"]
            candles.append({
                "date": row["trade_date"],
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "color": "#22c55e" if is_bullish else "#ef4444"  # Green or Red
            })
            volumes.append({
                "date": row["trade_date"],
                "volume": int(row["volume"]),
                "color": "#22c55e" if is_bullish else "#ef4444"
            })

        # Moving averages
        sma_20 = [{"date": row["trade_date"], "value": round(float(row["sma_20"]), 2)}
                  for _, row in df.iterrows() if pd.notna(row.get("sma_20"))]
        sma_50 = [{"date": row["trade_date"], "value": round(float(row["sma_50"]), 2)}
                  for _, row in df.iterrows() if pd.notna(row.get("sma_50"))]

        return {
            "symbol": symbol,
            "period": period,
            "candles": candles,
            "volumes": volumes,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "stats": {
                "high": round(float(df["high"].max()), 2),
                "low": round(float(df["low"].min()), 2),
                "avg_volume": int(df["volume"].mean()),
                "total_days": len(df)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/score-explanation")
async def get_score_explanation_endpoint():
    """Get detailed explanation of how scores are calculated"""
    return get_score_explanation()


@app.get("/api/available-dates")
async def get_available_dates():
    """Get list of dates with screening data available"""
    try:
        query = """
        SELECT DISTINCT screening_date, COUNT(*) as count
        FROM screener_results
        GROUP BY screening_date
        ORDER BY screening_date DESC
        LIMIT 30
        """
        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn)

        dates = [{"date": row["screening_date"], "count": row["count"]}
                 for _, row in df.iterrows()]

        # Also get EOD date range
        min_date, max_date = db.get_date_range()

        return {
            "screening_dates": dates,
            "data_range": {"min": min_date, "max": max_date}
        }

    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sectors")
async def get_sector_analysis():
    """Get sector-wise performance analysis"""
    try:
        # Get latest data with sector info
        query = """
        SELECT e.symbol, e.close, e.prev_close, e.volume, i.rsi_14
        FROM eod e
        JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
        """
        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn)

        if df.empty:
            return {"sectors": []}

        # Sector mapping (simplified)
        sector_map = {
            "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy",
            "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
            "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "KOTAKBANK": "Banking",
            "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma",
            "MARUTI": "Auto", "M&M": "Auto", "TATAMOTORS": "Auto", "EICHERMOT": "Auto",
            "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
            "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals",
            "LT": "Infrastructure", "DLF": "Realty", "TITAN": "Consumer",
            "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power"
        }

        df["sector"] = df["symbol"].map(sector_map).fillna("Other")
        df["change_pct"] = ((df["close"] - df["prev_close"]) / df["prev_close"]) * 100

        sector_stats = df.groupby("sector").agg({
            "change_pct": "mean",
            "rsi_14": "mean",
            "symbol": "count"
        }).reset_index()

        sector_stats.columns = ["sector", "avg_change", "avg_rsi", "stock_count"]
        sector_stats = sector_stats.sort_values("avg_change", ascending=False)

        sectors = []
        for _, row in sector_stats.iterrows():
            strength = "STRONG" if row["avg_rsi"] > 55 and row["avg_change"] > 0 else \
                       "MODERATE" if row["avg_rsi"] > 50 else "WEAK"
            sectors.append({
                "sector": row["sector"],
                "avg_change": round(row["avg_change"], 2),
                "avg_rsi": round(row["avg_rsi"], 1),
                "stock_count": int(row["stock_count"]),
                "strength": strength
            })

        return {"sectors": sectors}

    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/run")
async def run_screener_now(top_n: int = 25, capital_per_trade: float = 100000):
    """Run screener on latest available data"""
    try:
        query = """
        SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
               e.volume, e.turnover, e.prev_close,
               i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
        FROM eod e
        JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
        """

        with db.get_connection() as conn:
            df = pd.read_sql_query(query, conn)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available. Please ingest data first.")

        latest = get_latest_snapshot_per_symbol(df)
        results = run_screener(latest, top_n=top_n, capital_per_trade=capital_per_trade)

        if results.empty:
            return {"status": "success", "results": [], "message": "No candidates found"}

        screening_date = df.iloc[0]["trade_date"]
        db.save_screener_results(results, screening_date)

        output = []
        for _, row in results.iterrows():
            output.append({
                "symbol": row["symbol"],
                "score": row["score"],
                "close_price": row["close_price"],
                "entry_price": row["entry_price"],
                "stop_loss": row["stop_loss"],
                "target_price": row["target_price"],
                "risk_reward": row["risk_reward"],
                "position_size": row["position_size"],
                "metadata": json.loads(row["metadata"])
            })

        return {"status": "success", "results": output, "screening_date": screening_date}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running screener: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest/run", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest):
    """Run backtest over historical period"""
    try:
        with db.get_connection() as conn:
            all_data = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.trade_date >= ? AND e.trade_date <= ?
                ORDER BY e.trade_date
                """,
                conn,
                params=(request.start_date, request.end_date)
            )

        if all_data.empty:
            raise HTTPException(status_code=404, detail="No data for specified period")

        bt = Backtest(initial_capital=request.capital, max_positions=request.max_positions)
        dates = sorted(all_data["trade_date"].unique())

        for screening_date in dates[::5]:
            snapshot = all_data[all_data["trade_date"] == screening_date]
            snapshot = get_latest_snapshot_per_symbol(snapshot)
            candidates = run_screener(snapshot, top_n=request.max_positions,
                                      capital_per_trade=request.capital / request.max_positions)
            if not candidates.empty:
                bt.run(candidates, all_data, screening_date)

        stats = bt.get_overall_stats()
        return BacktestResult(**stats)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/overview")
async def get_stats_overview():
    """Get overview statistics - only counts stocks with current data"""
    try:
        # Check cache first
        cached = cache.get("stats_overview")
        if cached:
            return cached
        
        min_date, max_date = db.get_date_range()

        with db.get_connection() as conn:
            # Only count symbols that have data on the latest date (fresh stocks)
            cursor = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM eod WHERE trade_date = (SELECT MAX(trade_date) FROM eod)"
            )
            fresh_symbols_count = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM screener_results WHERE screening_date = (SELECT MAX(screening_date) FROM screener_results)"
            )
            latest_candidates = cursor.fetchone()[0]

        result = {
            "total_symbols": fresh_symbols_count,
            "date_range": {"min": min_date, "max": max_date},
            "latest_candidates": latest_candidates
        }
        
        # Cache for 5 minutes
        cache.set("stats_overview", result, ttl=300)
        
        return result

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest/latest")
async def ingest_latest_data(background_tasks: BackgroundTasks):
    """Download and process latest NSE data with retry for holidays"""
    try:
        # First check current data status
        current_latest_date = None
        current_stock_count = 0
        try:
            with db.get_connection() as conn:
                result = pd.read_sql_query("SELECT MAX(trade_date) as max_date FROM eod", conn)
                current_latest_date = result.iloc[0]['max_date']
                if current_latest_date:
                    count_result = pd.read_sql_query(
                        "SELECT COUNT(DISTINCT symbol) as cnt FROM eod WHERE trade_date = ?",
                        conn, params=[current_latest_date]
                    )
                    current_stock_count = count_result.iloc[0]['cnt']
        except Exception as e:
            logger.warning(f"Could not get current data status: {e}")
        
        ingester = NSEDataIngester(config.cache_dir, config.raw_dir)
        trade_date = ingester.get_latest_trading_day()

        # Try up to 10 days back to handle holidays and weekends
        csv_path = None
        attempted_dates = []
        for attempt in range(10):
            attempted_dates.append(trade_date.strftime('%Y-%m-%d'))
            logger.info(f"Attempting to download data for {trade_date.strftime('%Y-%m-%d')}")
            csv_path = ingester.download_bhavcopy(trade_date)

            if csv_path:
                break

            # Go back one more trading day
            trade_date = trade_date - timedelta(days=1)
            # Skip weekends
            while trade_date.weekday() >= 5:
                trade_date = trade_date - timedelta(days=1)

        if not csv_path:
            # Graceful response - data is up to date or NSE unavailable
            if current_latest_date:
                return IngestionStatus(
                    status="up_to_date",
                    message=f"NSE data not available for recent dates. Your data is current as of {current_latest_date} with {current_stock_count} stocks.",
                    records_processed=0,
                    date=current_latest_date
                )
            else:
                return IngestionStatus(
                    status="no_data",
                    message=f"Could not fetch NSE data. Tried dates: {', '.join(attempted_dates[:5])}. Please try again later.",
                    records_processed=0,
                    date=None
                )

        df = ingester.load_bhavcopy_csv(csv_path)
        records = db.upsert_eod_data(df)
        background_tasks.add_task(compute_and_store_indicators)
        
        # Invalidate cache after new data is ingested
        cache.clear()
        logger.info("Cache cleared after data ingestion")

        return IngestionStatus(
            status="success",
            message="Data ingested successfully",
            records_processed=records,
            date=trade_date.strftime("%Y-%m-%d")
        )

    except Exception as e:
        logger.error(f"Error ingesting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def compute_and_store_indicators():
    """Compute indicators for all symbols"""
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM eod ORDER BY symbol, trade_date", conn)

        if df.empty:
            return

        with_indicators = compute_indicators_for_all_symbols(df)
        indicators_df = extract_indicator_columns(with_indicators)
        db.upsert_indicators(indicators_df)

    except Exception as e:
        logger.error(f"Error computing indicators: {e}")


# Global state for tracking bulk download progress
_bulk_download_status = {
    "running": False,
    "progress": 0,
    "total_days": 0,
    "days_downloaded": 0,
    "current_date": None,
    "error": None,
    "completed": False,
    "last_updated": None
}


@app.post("/api/ingest/bulk")
async def ingest_bulk_historical_data(
    background_tasks: BackgroundTasks,
    years: int = Query(default=10, ge=1, le=15, description="Number of years of history to download")
):
    """
    Download and process historical NSE data for specified years.
    Only downloads data for fresh/active stocks (those with recent trading data).
    This runs in background and progress can be checked via /api/ingest/bulk/status
    """
    global _bulk_download_status
    
    if _bulk_download_status["running"]:
        return {
            "status": "already_running",
            "message": "Bulk download is already in progress. Check /api/ingest/bulk/status for progress."
        }
    
    # Get count of fresh stocks
    fresh_stocks_count = 0
    try:
        with db.get_connection() as conn:
            latest_date = pd.read_sql_query("SELECT MAX(trade_date) as max_date FROM eod", conn).iloc[0]['max_date']
            if latest_date:
                fresh_stocks_count = pd.read_sql_query(
                    "SELECT COUNT(DISTINCT symbol) as cnt FROM eod WHERE trade_date = ?",
                    conn, params=[latest_date]
                ).iloc[0]['cnt']
    except:
        pass
    
    # Calculate date range
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=years * 365)
    
    # Reset status
    _bulk_download_status = {
        "running": True,
        "progress": 0,
        "total_days": (end_date - start_date).days,
        "days_downloaded": 0,
        "current_date": None,
        "error": None,
        "fresh_stocks_count": fresh_stocks_count,
        "completed": False,
        "last_updated": datetime.now().isoformat(),
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    # Run download in background
    background_tasks.add_task(run_bulk_download, start_date, end_date)
    
    return {
        "status": "started",
        "message": f"Bulk download started for {years} years ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})",
        "total_days": _bulk_download_status["total_days"],
        "check_status_at": "/api/ingest/bulk/status"
    }


@app.get("/api/ingest/bulk/status")
async def get_bulk_download_status():
    """Get status of bulk data download"""
    global _bulk_download_status
    return convert_to_native(_bulk_download_status)


def run_bulk_download(start_date: datetime, end_date: datetime):
    """Background task to download historical data - only for fresh/active stocks"""
    global _bulk_download_status
    import time
    import requests
    import io
    import zipfile
    
    ARCHIVE_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{year}/{month}/cm{date}bhav.csv.zip"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    }
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Get fresh stocks list (those with recent data) - only update these for swing trading
    fresh_stocks = set()
    try:
        with db.get_connection() as conn:
            latest_date = pd.read_sql_query("SELECT MAX(trade_date) as max_date FROM eod", conn).iloc[0]['max_date']
            if latest_date:
                fresh_df = pd.read_sql_query(
                    "SELECT DISTINCT symbol FROM eod WHERE trade_date = ?",
                    conn, params=[latest_date]
                )
                fresh_stocks = set(fresh_df['symbol'].tolist())
        logger.info(f"Will filter to {len(fresh_stocks)} fresh stocks for swing trading")
    except Exception as e:
        logger.warning(f"Could not get fresh stocks list: {e}")
    
    # Initialize session by visiting NSE
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(2)
        # Get cookies
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
        time.sleep(1)
    except Exception as e:
        logger.warning(f"Could not initialize NSE session: {e}")
    
    all_dfs = []
    current = start_date
    trading_days_downloaded = 0
    consecutive_failures = 0
    
    try:
        while current <= end_date:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            
            _bulk_download_status["current_date"] = current.strftime("%Y-%m-%d")
            _bulk_download_status["last_updated"] = datetime.now().isoformat()
            
            # Build URL
            date_str = current.strftime("%d%b%Y").upper()
            year = current.year
            month = current.strftime("%b").upper()
            url = ARCHIVE_URL.format(year=year, month=month, date=date_str)
            
            try:
                response = session.get(url, timeout=30)
                
                if response.status_code == 200:
                    # Extract CSV from zip
                    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                        csv_name = zf.namelist()[0]
                        with zf.open(csv_name) as f:
                            df = pd.read_csv(f)
                    
                    # Standardize columns
                    df = df.rename(columns={
                        "SYMBOL": "symbol", "OPEN": "open", "HIGH": "high",
                        "LOW": "low", "CLOSE": "close", "PREVCLOSE": "prev_close",
                        "TOTTRDQTY": "volume", "TOTTRDVAL": "turnover",
                        "TIMESTAMP": "trade_date", "SERIES": "series"
                    })
                    
                    # Filter EQ series only
                    if "series" in df.columns:
                        df = df[df["series"] == "EQ"].copy()
                    
                    # Filter to only fresh/active stocks (for swing trading)
                    if fresh_stocks:
                        df = df[df["symbol"].isin(fresh_stocks)]
                    
                    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
                    
                    cols = ["symbol", "trade_date", "open", "high", "low", "close",
                            "volume", "turnover", "prev_close"]
                    cols = [c for c in cols if c in df.columns]
                    df = df[cols]
                    
                    if not df.empty:
                        all_dfs.append(df)
                        trading_days_downloaded += 1
                        consecutive_failures = 0
                        
                        logger.info(f"Downloaded {current.strftime('%Y-%m-%d')}: {len(df)} stocks (filtered)")
                    
                    # Store incrementally every 10 days to avoid memory issues
                    if len(all_dfs) >= 10:
                        combined = pd.concat(all_dfs, ignore_index=True)
                        db.upsert_eod_data(combined)
                        all_dfs = []
                        logger.info(f"Stored batch, total {trading_days_downloaded} trading days")
                
                elif response.status_code == 404:
                    # Holiday - expected
                    consecutive_failures = 0
                elif response.status_code == 403:
                    # Blocked - need to refresh session
                    consecutive_failures += 1
                    logger.warning(f"403 Forbidden - refreshing session...")
                    try:
                        session.get("https://www.nseindia.com", timeout=10)
                        time.sleep(3)
                    except:
                        pass
                else:
                    consecutive_failures += 1
                    
            except Exception as e:
                logger.warning(f"Error downloading {current.strftime('%Y-%m-%d')}: {e}")
                consecutive_failures += 1
            
            # Update progress
            days_elapsed = (current - start_date).days
            _bulk_download_status["progress"] = min(100, int(days_elapsed / _bulk_download_status["total_days"] * 100))
            _bulk_download_status["days_downloaded"] = trading_days_downloaded
            
            # Rate limiting
            time.sleep(1.5)
            
            # Stop if too many failures
            if consecutive_failures >= 10:
                _bulk_download_status["error"] = "Too many consecutive failures - NSE may be blocking"
                break
            
            current += timedelta(days=1)
        
        # Store remaining data
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            db.upsert_eod_data(combined)
        
        # Compute indicators
        _bulk_download_status["current_date"] = "Computing indicators..."
        logger.info("Computing indicators for all data...")
        
        compute_and_store_indicators()
        
        _bulk_download_status["running"] = False
        _bulk_download_status["completed"] = True
        _bulk_download_status["progress"] = 100
        _bulk_download_status["current_date"] = "Complete"
        _bulk_download_status["last_updated"] = datetime.now().isoformat()
        
        logger.info(f"Bulk download complete: {trading_days_downloaded} trading days")
        
    except Exception as e:
        logger.error(f"Bulk download error: {e}")
        _bulk_download_status["running"] = False
        _bulk_download_status["error"] = str(e)
        _bulk_download_status["last_updated"] = datetime.now().isoformat()


# ==================== ENHANCED SCREENER ENDPOINTS ====================

@app.get("/api/filters/summary")
async def get_filters_summary():
    """Get summary of all available filters and their purpose"""
    return get_filter_summary()


@app.get("/api/market-regime")
async def get_market_regime():
    """Check current market regime (bullish/bearish/neutral)"""
    try:
        # Get NIFTY 50 data (symbol ^NSEI or NIFTY)
        with db.get_connection() as conn:
            nifty_df = pd.read_sql_query(
                """
                SELECT trade_date, close, high, low, open, volume
                FROM eod
                WHERE symbol IN ('^NSEI', 'NIFTY', 'NIFTY50', '^NIFTY')
                ORDER BY trade_date DESC
                LIMIT 250
                """,
                conn
            )

        if nifty_df.empty:
            # Try to calculate from average of all stocks
            nifty_df = pd.read_sql_query(
                """
                SELECT trade_date, AVG(close) as close, AVG(high) as high,
                       AVG(low) as low, AVG(open) as open, SUM(volume) as volume
                FROM eod
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 250
                """,
                conn
            )

        if nifty_df.empty:
            return {
                "regime": "UNKNOWN",
                "allow_trading": True,
                "reason": "No market data available",
                "nifty_trend": "N/A"
            }

        nifty_df = nifty_df.sort_values("trade_date")
        regime = MarketRegimeFilter.check_market_regime(nifty_df)

        return regime

    except Exception as e:
        logger.error(f"Error checking market regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-rotation")
async def get_sector_rotation(top_n: int = 3):
    """Get sector rotation analysis - identifies hot sectors"""
    try:
        with db.get_connection() as conn:
            # Get latest data with sectors
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.close, e.volume,
                       i.sma_50, i.rsi_14, i.atr_14
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
                """,
                conn
            )

        if df.empty:
            return {"hot_sectors": [], "sector_ranking": [], "reason": "No data available"}

        # Add sector information from SECTOR_MAP
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Calculate basic metrics for sector analysis
        df["roc_10"] = 0  # Would need historical data
        df["relative_strength"] = 1
        df["total_score"] = 10

        sector_analysis = SectorRotationFilter.analyze_sectors(df, top_n=top_n)

        return sector_analysis

    except Exception as e:
        logger.error(f"Error analyzing sectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-analysis")
async def get_comprehensive_sector_analysis():
    """
    Get comprehensive sector rotation analysis with investment recommendations.

    Returns:
    - Sector rankings with scores
    - Phase identification (Leading, Improving, Lagging, etc.)
    - Investment recommendations (Overweight, Neutral, Underweight)
    - Top stocks per sector
    - Strategy recommendation
    """
    try:
        with db.get_connection() as conn:
            # Get all stock data with indicators
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector information
        try:
            df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        except ImportError:
            df["sector"] = "Unknown"

        # Add advanced indicators
        df = add_advanced_indicators(df)
        df = score_for_swing_trade(df)

        # Calculate additional metrics
        df["atr_pct"] = (df["atr_14"] / df["close"]) * 100
        df["vol_ratio"] = df["volume"] / df["vol_ma_20"].fillna(df["volume"])
        df["roc_10"] = df.get("roc_10", 0)
        df["relative_strength"] = df.get("relative_strength", 1)

        # Run comprehensive sector analysis
        analysis = analyze_sector_rotation(df)

        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in sector analysis: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector/{sector_name}/stocks")
async def get_sector_stocks(sector_name: str, limit: int = 10):
    """Get all stocks in a specific sector with their scores"""
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.open, e.high, e.low, e.close, e.volume,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector
        try:
            df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        except ImportError:
            df["sector"] = "Unknown"

        # Filter by sector
        sector_df = df[df["sector"].str.lower() == sector_name.lower()]

        if sector_df.empty:
            raise HTTPException(status_code=404, detail=f"Sector '{sector_name}' not found")

        # Add indicators and score
        sector_df = add_advanced_indicators(sector_df)
        sector_df = score_for_swing_trade(sector_df)

        # Sort by score
        sector_df = sector_df.sort_values("total_score", ascending=False)

        stocks = []
        for _, row in sector_df.head(limit).iterrows():
            stocks.append({
                "symbol": row["symbol"],
                "close": float(row["close"]),
                "score": int(row.get("total_score", 0)),
                "rsi": float(row.get("rsi_14", 50)),
                "above_sma20": bool(row["close"] > row.get("sma_20", 0)),
                "above_sma50": bool(row["close"] > row.get("sma_50", 0)),
                "strength": "STRONG" if row.get("total_score", 0) >= 15 else
                           "MODERATE" if row.get("total_score", 0) >= 12 else "WEAK"
            })

        sector_info = SECTOR_INFO.get(sector_name, SECTOR_INFO["Unknown"])

        return {
            "sector": sector_name,
            "sector_info": sector_info,
            "total_stocks": len(sector_df),
            "stocks": stocks
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/enhanced")
async def run_enhanced_screener_endpoint(
    top_n: int = 10,
    capital_per_trade: float = 100000,
    min_score: int = 12,
    apply_market_filter: bool = True,
    apply_sector_filter: bool = True,
    apply_sr_filter: bool = True,
    apply_mtf_filter: bool = True,
    apply_fundamental_filter: bool = True,
    top_sectors: int = 3
):
    """
    Run enhanced screener with all win-rate improvement filters.

    Filters applied:
    1. Market Regime - Only trade in bullish markets
    2. Sector Rotation - Only trade hot sectors
    3. Support/Resistance - Prefer entries near support
    4. Multi-timeframe - Weekly + Daily alignment
    5. Fundamental - Avoid troubled stocks
    6. Higher minimum score (12 instead of 10)
    """
    try:
        # Get stock data with indicators
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
                """,
                conn
            )

            # Get NIFTY data for market regime
            nifty_df = pd.read_sql_query(
                """
                SELECT trade_date, close, high, low, open, volume
                FROM eod
                ORDER BY trade_date DESC
                LIMIT 250
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available. Please ingest data first.")

        # Add sector information
        try:
            df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        except ImportError:
            df["sector"] = "Unknown"

        # Add advanced indicators
        df = add_advanced_indicators(df)
        df = score_for_swing_trade(df)

        # Calculate additional fields needed for filters
        df["atr_pct"] = (df["atr_14"] / df["close"]) * 100
        df["vol_ratio"] = df["volume"] / df["vol_ma_20"].fillna(df["volume"])
        df["risk_reward"] = 2.0  # Default, will be recalculated
        df["dist_from_20d_high"] = ((df["hh_20"] - df["close"]) / df["hh_20"]) * 100
        df["dist_from_52w_high"] = df["dist_from_20d_high"]  # Simplified

        # Prepare NIFTY data for market regime
        if not nifty_df.empty:
            nifty_agg = nifty_df.groupby("trade_date").agg({
                "close": "mean",
                "high": "mean",
                "low": "mean",
                "open": "mean",
                "volume": "sum"
            }).reset_index()
            nifty_agg = nifty_agg.sort_values("trade_date")
        else:
            nifty_agg = None

        # Run enhanced screener
        results = run_enhanced_screener(
            df=df,
            nifty_df=nifty_agg,
            top_n=top_n,
            capital_per_trade=capital_per_trade,
            min_score=min_score,
            apply_market_filter=apply_market_filter,
            apply_sector_filter=apply_sector_filter,
            top_sectors=top_sectors,
            apply_sr_filter=apply_sr_filter,
            apply_mtf_filter=apply_mtf_filter,
            apply_fundamental_filter=apply_fundamental_filter
        )

        # Save results to database
        if results["candidates"]:
            screening_date = df.iloc[0]["trade_date"]
            results_df = pd.DataFrame(results["candidates"])
            results_df["metadata"] = results_df["metadata"].apply(json.dumps)
            db.save_screener_results(results_df, screening_date)

        return {
            "status": "success",
            "screening_date": df.iloc[0]["trade_date"] if not df.empty else None,
            "filters_applied": results.get("filters_applied", []),
            "market_regime": results.get("filters_status", {}).get("market_regime", {}),
            "sector_rotation": results.get("filters_status", {}).get("sector_rotation", {}),
            "candidates": results.get("candidates", []),
            "rejected_count": len(results.get("rejected", [])),
            "stats": results.get("stats", {}),
            "top_rejections": results.get("rejected", [])[:5]  # Show top 5 rejections
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running enhanced screener: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/position-size/{symbol}")
async def calculate_position_size(
    symbol: str,
    capital: float = 100000,
    risk_pct: float = 2.0
):
    """Calculate risk-adjusted position size for a stock"""
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.close, i.atr_14
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.symbol = ?
                ORDER BY e.trade_date DESC
                LIMIT 1
                """,
                conn,
                params=(symbol,)
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        row = df.iloc[0]
        row = pd.Series(row)

        position = RiskAdjustedPositionSizer.calculate_position(
            row,
            capital_per_trade=capital,
            max_risk_pct=risk_pct
        )

        return {
            "symbol": symbol,
            "current_price": float(row["close"]),
            "atr_14": float(row["atr_14"]) if pd.notna(row["atr_14"]) else None,
            "position": position
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/comprehensive")
async def get_comprehensive_stock_analysis(
    symbol: str,
    capital: float = Query(default=100000, description="Investment capital")
):
    """
    Get comprehensive stock analysis including:
    - Current price and technicals
    - Investment zones (entry, stop loss, targets)
    - Support/Resistance levels
    - Trend analysis
    - Buy/Sell recommendation
    - Position sizing
    """
    try:
        symbol = symbol.upper().strip()
        
        with db.get_connection() as conn:
            # Get price history with indicators
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.symbol = ?
                ORDER BY e.trade_date DESC
                LIMIT 250
                """,
                conn,
                params=(symbol,)
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        df = df.sort_values("trade_date")
        latest = df.iloc[-1]
        
        # Get sector
        sector = SECTOR_MAP.get(symbol, "Unknown")
        
        # Calculate metrics
        current_price = float(latest["close"])
        prev_close = float(latest.get("prev_close", current_price))
        daily_change = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0
        
        # Technical indicators
        rsi = float(latest.get("rsi_14", 50)) if pd.notna(latest.get("rsi_14")) else 50
        sma_20 = float(latest.get("sma_20", current_price)) if pd.notna(latest.get("sma_20")) else current_price
        sma_50 = float(latest.get("sma_50", current_price)) if pd.notna(latest.get("sma_50")) else current_price
        atr = float(latest.get("atr_14", current_price * 0.02)) if pd.notna(latest.get("atr_14")) else current_price * 0.02
        
        # 52-week high/low
        high_52w = float(df["high"].max())
        low_52w = float(df["low"].min())
        
        # 20-day high/low
        recent_20 = df.tail(20)
        high_20d = float(recent_20["high"].max())
        low_20d = float(recent_20["low"].min())
        
        # Distance from highs/lows
        dist_from_52w_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else 0
        dist_from_20d_high = ((high_20d - current_price) / high_20d * 100) if high_20d > 0 else 0
        
        # Trend Analysis
        trend_direction = "BULLISH" if current_price > sma_20 > sma_50 else \
                         "BEARISH" if current_price < sma_20 < sma_50 else "NEUTRAL"
        
        price_vs_sma20 = ((current_price - sma_20) / sma_20 * 100) if sma_20 > 0 else 0
        price_vs_sma50 = ((current_price - sma_50) / sma_50 * 100) if sma_50 > 0 else 0
        
        # RSI interpretation
        if rsi >= 70:
            rsi_signal = "OVERBOUGHT"
            rsi_action = "Consider waiting for pullback"
        elif rsi >= 55:
            rsi_signal = "BULLISH"
            rsi_action = "Good momentum for entry"
        elif rsi >= 45:
            rsi_signal = "NEUTRAL"
            rsi_action = "Wait for clearer signal"
        elif rsi >= 30:
            rsi_signal = "BEARISH"
            rsi_action = "Caution - weakness present"
        else:
            rsi_signal = "OVERSOLD"
            rsi_action = "Potential bounce zone"
        
        # Volume analysis
        vol_ma = float(latest.get("vol_ma_20", 1)) if pd.notna(latest.get("vol_ma_20")) else 1
        vol_ratio = float(latest["volume"]) / vol_ma if vol_ma > 0 else 1
        volume_signal = "HIGH" if vol_ratio >= 2 else "ABOVE AVERAGE" if vol_ratio >= 1.2 else "NORMAL" if vol_ratio >= 0.8 else "LOW"
        
        # ===== INVESTMENT ZONES =====
        # Entry Zone: Current price to slight pullback
        entry_zone_high = round(current_price, 2)
        entry_zone_low = round(current_price * 0.98, 2)  # 2% below current
        
        # If price is extended above SMA20, suggest waiting for pullback
        if price_vs_sma20 > 5:
            entry_zone_high = round(sma_20 * 1.02, 2)
            entry_zone_low = round(sma_20 * 0.99, 2)
        
        # Stop Loss: 1-1.5x ATR below entry
        stop_loss = round(entry_zone_low - (atr * 1.0), 2)
        stop_loss_pct = round(((entry_zone_low - stop_loss) / entry_zone_low) * 100, 2)
        
        # Targets based on ATR
        target_1 = round(current_price + (atr * 1.5), 2)  # 1.5R
        target_2 = round(current_price + (atr * 2.5), 2)  # 2.5R
        target_3 = round(current_price + (atr * 4.0), 2)  # 4R (swing target)
        
        # Calculate reward percentages
        target_1_pct = round(((target_1 - current_price) / current_price) * 100, 2)
        target_2_pct = round(((target_2 - current_price) / current_price) * 100, 2)
        target_3_pct = round(((target_3 - current_price) / current_price) * 100, 2)
        
        # Risk:Reward ratio
        risk_amount = current_price - stop_loss
        reward_amount = target_2 - current_price
        risk_reward = round(reward_amount / risk_amount, 2) if risk_amount > 0 else 0
        
        # Position Sizing
        risk_per_share = current_price - stop_loss
        max_risk_amount = capital * 0.02  # 2% risk
        shares = int(max_risk_amount / risk_per_share) if risk_per_share > 0 else 0
        position_value = round(shares * current_price, 2)
        
        # ===== OVERALL RECOMMENDATION =====
        score = 0
        reasons = []
        
        # Trend score
        if trend_direction == "BULLISH":
            score += 25
            reasons.append("✅ Bullish trend (price > SMA20 > SMA50)")
        elif trend_direction == "NEUTRAL":
            score += 10
            reasons.append("⚠️ Neutral trend")
        else:
            reasons.append("❌ Bearish trend")
        
        # RSI score
        if 55 <= rsi <= 70:
            score += 25
            reasons.append(f"✅ RSI {rsi:.1f} in constructive zone")
        elif 45 <= rsi < 55:
            score += 10
            reasons.append(f"⚠️ RSI {rsi:.1f} neutral")
        elif rsi > 70:
            score += 5
            reasons.append(f"⚠️ RSI {rsi:.1f} overbought - wait for pullback")
        else:
            reasons.append(f"❌ RSI {rsi:.1f} showing weakness")
        
        # Volume score
        if vol_ratio >= 1.5:
            score += 15
            reasons.append(f"✅ Volume {vol_ratio:.1f}x average - strong interest")
        elif vol_ratio >= 1.0:
            score += 10
            reasons.append(f"⚠️ Volume at average")
        else:
            reasons.append(f"⚠️ Volume below average")
        
        # Distance from high
        if dist_from_20d_high <= 3:
            score += 20
            reasons.append("✅ Near 20-day high - breakout potential")
        elif dist_from_20d_high <= 10:
            score += 10
            reasons.append(f"⚠️ {dist_from_20d_high:.1f}% from 20-day high")
        
        # Risk:Reward
        if risk_reward >= 2:
            score += 15
            reasons.append(f"✅ Risk:Reward {risk_reward}:1 favorable")
        elif risk_reward >= 1.5:
            score += 10
            reasons.append(f"⚠️ Risk:Reward {risk_reward}:1 acceptable")
        else:
            reasons.append(f"❌ Risk:Reward {risk_reward}:1 poor")
        
        # Determine action
        if score >= 70:
            action = "STRONG BUY"
            action_color = "green"
        elif score >= 50:
            action = "BUY"
            action_color = "green"
        elif score >= 35:
            action = "HOLD/WAIT"
            action_color = "yellow"
        else:
            action = "AVOID"
            action_color = "red"
        
        # Support/Resistance levels
        supports = [
            {"level": round(sma_20, 2), "name": "SMA 20"},
            {"level": round(sma_50, 2), "name": "SMA 50"},
            {"level": round(low_20d, 2), "name": "20-Day Low"},
        ]
        resistances = [
            {"level": round(high_20d, 2), "name": "20-Day High"},
            {"level": round(high_52w, 2), "name": "52-Week High"},
        ]
        
        return {
            "symbol": symbol,
            "sector": sector,
            "last_updated": latest["trade_date"],
            
            "price_data": {
                "current_price": current_price,
                "prev_close": prev_close,
                "daily_change_pct": round(daily_change, 2),
                "high_52w": high_52w,
                "low_52w": low_52w,
                "high_20d": high_20d,
                "low_20d": low_20d,
                "dist_from_52w_high_pct": round(dist_from_52w_high, 2),
                "dist_from_20d_high_pct": round(dist_from_20d_high, 2)
            },
            
            "technicals": {
                "rsi_14": round(rsi, 2),
                "rsi_signal": rsi_signal,
                "rsi_action": rsi_action,
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "price_vs_sma20_pct": round(price_vs_sma20, 2),
                "price_vs_sma50_pct": round(price_vs_sma50, 2),
                "atr_14": round(atr, 2),
                "atr_pct": round((atr / current_price) * 100, 2),
                "volume": int(latest["volume"]),
                "vol_avg_20": int(vol_ma),
                "vol_ratio": round(vol_ratio, 2),
                "volume_signal": volume_signal
            },
            
            "trend": {
                "direction": trend_direction,
                "above_sma20": current_price > sma_20,
                "above_sma50": current_price > sma_50,
                "sma20_above_sma50": sma_20 > sma_50
            },
            
            "investment_zones": {
                "entry_zone": {
                    "low": entry_zone_low,
                    "high": entry_zone_high,
                    "note": "Ideal entry range" if price_vs_sma20 <= 5 else "Wait for pullback to this zone"
                },
                "stop_loss": {
                    "price": stop_loss,
                    "pct_from_entry": stop_loss_pct
                },
                "targets": [
                    {"name": "Target 1 (1.5R)", "price": target_1, "pct_gain": target_1_pct},
                    {"name": "Target 2 (2.5R)", "price": target_2, "pct_gain": target_2_pct},
                    {"name": "Target 3 (Swing)", "price": target_3, "pct_gain": target_3_pct}
                ],
                "risk_reward_ratio": risk_reward
            },
            
            "position_sizing": {
                "capital": capital,
                "risk_pct": 2.0,
                "max_risk_amount": max_risk_amount,
                "shares": shares,
                "position_value": position_value,
                "pct_of_capital": round((position_value / capital) * 100, 2) if capital > 0 else 0
            },
            
            "support_resistance": {
                "supports": sorted(supports, key=lambda x: x["level"], reverse=True),
                "resistances": sorted(resistances, key=lambda x: x["level"])
            },
            
            "recommendation": {
                "action": action,
                "action_color": action_color,
                "score": score,
                "max_score": 100,
                "reasons": reasons
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stocks/search")
async def search_stocks(q: str = Query(..., min_length=1, description="Search query")):
    """Search stocks by symbol or name"""
    try:
        q = q.upper().strip()
        
        # Get all symbols from database
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT DISTINCT symbol FROM eod 
                WHERE symbol LIKE ?
                ORDER BY symbol
                LIMIT 20
                """,
                conn,
                params=(f"%{q}%",)
            )
        
        results = []
        for _, row in df.iterrows():
            symbol = row["symbol"]
            sector = SECTOR_MAP.get(symbol, "Unknown")
            results.append({
                "symbol": symbol,
                "sector": sector
            })
        
        return {"results": results}
    
    except Exception as e:
        logger.error(f"Error searching stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/financials")
async def get_stock_financial_analysis(symbol: str):
    """
    Get comprehensive financial analysis for a stock.
    
    Evaluates stock like a financial advisor would:
    - Financial Strength Score (0-100)
    - Balance Sheet Summary
    - Income Statement (5-year trend)
    - Cash Flow Analysis
    - Key Ratios (PE, PB, ROE, D/E, etc.)
    - Pros & Cons Analysis
    - Investment Recommendation
    """
    try:
        symbol = symbol.upper().strip()
        
        # Fetch financial data from Yahoo Finance
        financials = fetch_financial_data(symbol)
        
        if "error" in financials:
            raise HTTPException(
                status_code=404, 
                detail=f"Could not fetch financials for {symbol}: {financials.get('message', financials.get('error'))}"
            )
        
        return convert_to_native(financials)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching financial analysis for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/entry-analysis")
async def analyze_entry(symbol: str):
    """Analyze if current price is a good entry point"""
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.symbol = ?
                ORDER BY e.trade_date DESC
                LIMIT 100
                """,
                conn,
                params=(symbol,)
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        row = df.iloc[0]

        # Support/Resistance analysis
        sr_info = SupportResistanceFilter.calculate_sr_levels(row)

        # Fundamental check
        row["roc_10"] = 0
        row["dist_from_52w_high"] = ((df["high"].max() - row["close"]) / df["high"].max()) * 100
        fundamental_info = FundamentalFilter.check_fundamentals(row)

        # Position sizing
        position = RiskAdjustedPositionSizer.calculate_position(
            row,
            setup_quality=sr_info["entry_quality"]
        )

        return {
            "symbol": symbol,
            "current_price": float(row["close"]),
            "support_resistance": sr_info,
            "fundamental_health": fundamental_info,
            "recommended_position": position,
            "entry_recommendation": {
                "quality": sr_info["entry_quality"],
                "action": "ENTER" if sr_info["entry_score"] >= 2 and fundamental_info["allow"] else "WAIT",
                "reason": f"Entry quality: {sr_info['entry_quality']}, Distance from support: {sr_info['support_distance_pct']:.1f}%"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-heatmap")
async def get_sector_heatmap(
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)")
):
    """
    Get sector performance heatmap data for a date range.
    Returns daily performance for each sector to build a heatmap.
    """
    try:
        with db.get_connection() as conn:
            # Get date range if not provided
            if not start_date or not end_date:
                min_date, max_date = db.get_date_range()
                if not start_date:
                    # Default to last 30 trading days
                    start_date = (datetime.strptime(max_date, "%Y-%m-%d") - timedelta(days=45)).strftime("%Y-%m-%d")
                if not end_date:
                    end_date = max_date

            # Get all EOD data for the date range
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.close, e.prev_close, e.volume
                FROM eod e
                WHERE e.trade_date >= ? AND e.trade_date <= ?
                ORDER BY e.trade_date
                """,
                conn,
                params=(start_date, end_date)
            )

        if df.empty:
            return {
                "error": "No data available for this date range",
                "start_date": start_date,
                "end_date": end_date,
                "heatmap_data": [],
                "sectors": []
            }

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Calculate daily change percentage
        df["change_pct"] = ((df["close"] - df["prev_close"]) / df["prev_close"]) * 100
        df = df.dropna(subset=["change_pct"])

        # Get unique dates and sectors
        dates = sorted(df["trade_date"].unique())
        sectors = sorted([s for s in df["sector"].unique() if s != "Unknown"])

        # Build heatmap data
        heatmap_data = []

        for date in dates:
            date_data = df[df["trade_date"] == date]
            daily_sector_perf = {}

            for sector in sectors:
                sector_stocks = date_data[date_data["sector"] == sector]
                if len(sector_stocks) > 0:
                    avg_change = sector_stocks["change_pct"].mean()
                    stock_count = len(sector_stocks)
                    positive_count = (sector_stocks["change_pct"] > 0).sum()

                    daily_sector_perf[sector] = {
                        "change_pct": round(float(avg_change), 2),
                        "stock_count": int(stock_count),
                        "positive_count": int(positive_count),
                        "breadth": round(float(positive_count / stock_count * 100), 1) if stock_count > 0 else 0
                    }
                else:
                    daily_sector_perf[sector] = None

            heatmap_data.append({
                "date": date,
                "sectors": daily_sector_perf
            })

        # Calculate period summary for each sector
        sector_summary = []
        for sector in sectors:
            sector_df = df[df["sector"] == sector]
            if len(sector_df) == 0:
                continue

            # Get cumulative return
            first_date_data = sector_df[sector_df["trade_date"] == sector_df["trade_date"].min()]
            last_date_data = sector_df[sector_df["trade_date"] == sector_df["trade_date"].max()]

            if len(first_date_data) > 0 and len(last_date_data) > 0:
                start_price = first_date_data["close"].mean()
                end_price = last_date_data["close"].mean()
                period_return = ((end_price - start_price) / start_price) * 100 if start_price > 0 else 0
            else:
                period_return = 0

            avg_daily = sector_df.groupby("trade_date")["change_pct"].mean().mean()
            positive_days = (sector_df.groupby("trade_date")["change_pct"].mean() > 0).sum()
            total_days = len(sector_df["trade_date"].unique())

            sector_summary.append({
                "sector": sector,
                "period_return": round(float(period_return), 2),
                "avg_daily_change": round(float(avg_daily), 2),
                "positive_days": int(positive_days),
                "total_days": int(total_days),
                "win_rate": round(float(positive_days / total_days * 100) if total_days > 0 else 0, 1),
                "stock_count": int(sector_df["symbol"].nunique())
            })

        # Sort by period return
        sector_summary = sorted(sector_summary, key=lambda x: x["period_return"], reverse=True)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": len(dates),
            "sectors": sectors,
            "sector_summary": sector_summary,
            "heatmap_data": heatmap_data
        }

    except Exception as e:
        logger.error(f"Error generating sector heatmap: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ULTIMATE SCREENER ENDPOINTS ====================

@app.get("/api/screener/ultimate/methodology")
async def get_ultimate_methodology():
    """Get detailed explanation of ultimate screener methodology"""
    return get_screener_summary()


@app.post("/api/screener/ultimate")
async def run_ultimate_screener_endpoint(
    top_n: int = 20,
    capital_per_trade: float = 100000,
    min_score: float = 50,
    require_pattern: bool = True,
    require_trend: bool = True,
    sector_filter: bool = True,
    max_risk_pct: float = 5.0
):
    """
    Run the Ultimate Swing Screener with all advanced filters.

    This screener combines:
    1. Candlestick Pattern Recognition (15 points max)
    2. Trend Strength - ADX, Supertrend, MA alignment (10 points max)
    3. Volume Analysis (4 points max)
    4. Entry Quality - Support/Resistance proximity (4 points max)
    5. Momentum - RSI, MACD, ROC (6 points max)
    6. Relative Strength vs NIFTY (5 points max)

    Parameters:
    - top_n: Number of top stocks to return (default 20)
    - capital_per_trade: Capital per position for sizing (default 100000)
    - min_score: Minimum ultimate score percentage 0-100 (default 50)
    - require_pattern: Require at least one bullish pattern (default True)
    - require_trend: Require positive trend strength >= 4 (default True)
    - sector_filter: Only trade stocks in top performing sectors (default True)
    - max_risk_pct: Maximum risk per trade percentage (default 5.0)
    """
    try:
        with db.get_connection() as conn:
            # Get all historical data for pattern calculation
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.symbol, e.trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available. Please download data first.")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Calculate pattern scores and trend strength for each symbol
        logger.info("Calculating patterns and trend strength for all symbols...")
        all_processed = []

        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("trade_date").copy()

            # Calculate patterns
            group = calculate_pattern_score(group)

            # Calculate trend strength (includes Supertrend and ADX)
            group = calculate_trend_strength(group)

            all_processed.append(group)

        full_df = pd.concat(all_processed, ignore_index=True)

        # Calculate relative strength if we have NIFTY data
        nifty_df = full_df[full_df["symbol"] == "NIFTY50"]
        if not nifty_df.empty:
            nifty_returns = nifty_df.set_index("trade_date")["close"].pct_change()

            result_dfs = []
            for symbol, group in full_df.groupby("symbol"):
                if symbol == "NIFTY50":
                    continue
                group = group.sort_values("trade_date").copy()
                stock_returns = group.set_index("trade_date")["close"].pct_change()

                stock_cum = (1 + stock_returns).rolling(20).apply(lambda x: x.prod() - 1)
                nifty_cum = (1 + nifty_returns).rolling(20).apply(lambda x: x.prod() - 1)

                rs = stock_cum / nifty_cum.reindex(stock_cum.index)
                rs = rs.fillna(1.0).replace([np.inf, -np.inf], 1.0)

                group = group.reset_index(drop=True)
                group["relative_strength"] = rs.values[-len(group):]
                result_dfs.append(group)

            full_df = pd.concat(result_dfs, ignore_index=True)
        else:
            full_df["relative_strength"] = 1.0

        # Get latest data for screening
        latest_date = full_df["trade_date"].max()

        # Run the ultimate screener
        logger.info(f"Running ultimate screener on {latest_date}...")
        results = run_ultimate_screener(
            df=full_df,
            top_n=top_n,
            capital_per_trade=capital_per_trade,
            min_score=min_score,
            require_pattern=require_pattern,
            require_trend=require_trend,
            sector_filter=sector_filter,
            max_risk_pct=max_risk_pct
        )

        # Save results to database
        if results["candidates"]:
            results_df = pd.DataFrame([{
                "symbol": c["symbol"],
                "score": c["score"],
                "close_price": c["close_price"],
                "entry_price": c["entry_price"],
                "stop_loss": c["stop_loss"],
                "target_price": c["target_price"],
                "risk_reward": c["risk_reward"],
                "position_size": c["position_size"],
                "metadata": json.dumps(c["metadata"])
            } for c in results["candidates"]])

            db.save_screener_results(results_df, latest_date)

        return convert_to_native({
            "status": results.get("status", "success"),
            "screening_date": results.get("screening_date"),
            "filters_applied": results.get("filters_applied", []),
            "stats": results.get("stats", {}),
            "sector_analysis": results.get("sector_analysis", {}),
            "candidates": results.get("candidates", []),
            "rejected_sample": results.get("rejected", [])[:10]
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running ultimate screener: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/elite")
async def run_elite_screener_endpoint(
    top_n: int = 2,
    capital_per_trade: float = 100000,
    min_score: int = 70,
    min_price: float = 100,
    use_strict_filters: bool = True
):
    """
    Run the Elite Momentum Screener v2.0 - optimized for 80%+ win rate.
    
    UPGRADED FILTERS for institutional-grade stock selection:
    - Market Regime: Only trade when NIFTY is bullish
    - Relative Strength: Stocks must outperform NIFTY by 3%+
    - Volume Climax: 2x volume requirement (upgraded from 1.5x)
    - Quality Gate: Filters out troubled stocks
    - Dynamic Exits: ATR-based targets with time decay
    
    Based on 150 weeks of backtesting:
    - Previous Win Rate: 68.4% → Target: 80%+
    - Avg Return per Trade: +0.47%
    - Profit Factor: 1.45 → Target: 1.8+
    
    Parameters:
    - top_n: Number of picks (default 2 for optimal results)
    - capital_per_trade: Capital per position (default 100000)
    - min_score: Minimum elite score 0-100 (default 70)
    - min_price: Minimum stock price (default 100)
    - use_strict_filters: Enable v2.0 strict filters for higher win rate (default True)
    """
    try:
        with db.get_connection() as conn:
            # First get the latest date to filter fresh stocks only
            latest_date = pd.read_sql_query("SELECT MAX(trade_date) as max_date FROM eod", conn).iloc[0]['max_date']
            
            # Get only symbols that have data on the latest date (fresh stocks)
            fresh_symbols = pd.read_sql_query(
                "SELECT DISTINCT symbol FROM eod WHERE trade_date = ?",
                conn,
                params=[latest_date]
            )['symbol'].tolist()
            
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.symbol, e.trade_date
                """,
                conn
            )
            
            # Fetch NIFTY 50 data for market regime check
            nifty_df = pd.read_sql_query(
                """
                SELECT trade_date, close 
                FROM eod 
                WHERE symbol IN ('NIFTY', 'NIFTY50', '^NSEI')
                ORDER BY trade_date
                """,
                conn
            )
            
            # If no NIFTY data in DB, try to use a proxy (banking index or large cap)
            if nifty_df.empty:
                # Use HDFCBANK as proxy (highly correlated with NIFTY)
                nifty_df = pd.read_sql_query(
                    """
                    SELECT trade_date, close 
                    FROM eod 
                    WHERE symbol = 'HDFCBANK'
                    ORDER BY trade_date
                    """,
                    conn
                )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available. Please download data first.")

        # Filter to only include fresh stocks (those with current data)
        df = df[df["symbol"].isin(fresh_symbols)]
        
        if df.empty:
            raise HTTPException(status_code=404, detail="No stocks with current data available.")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        
        logger.info(f"Running elite screener v2.0 on {latest_date} with {len(fresh_symbols)} fresh stocks...")
        
        # Run the elite screener with NIFTY data for market regime check
        results = run_elite_screener(
            df=df,
            top_n=top_n,
            capital_per_trade=capital_per_trade,
            min_score=min_score,
            min_price=min_price,
            sector_filter=True,
            nifty_df=nifty_df if not nifty_df.empty else None,
            use_strict_filters=use_strict_filters
        )

        # Save results to database
        if results.get("candidates"):
            results_df = pd.DataFrame([{
                "symbol": c["symbol"],
                "score": c["score"],
                "close_price": c["close_price"],
                "entry_price": c["entry_price"],
                "stop_loss": c["stop_loss"],
                "target_price": c["target_price"],
                "risk_reward": c["risk_reward"],
                "position_size": c["position_size"],
                "metadata": json.dumps(c.get("metrics", {}))
            } for c in results["candidates"]])

            db.save_screener_results(results_df, latest_date)

        return convert_to_native(results)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running elite screener: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/elite/methodology")
async def get_elite_methodology_endpoint():
    """Get the elite screener methodology and backtest results."""
    return convert_to_native(get_elite_methodology())


# ============== MULTIBAGGER SCREENER ENDPOINTS ==============

@app.post("/api/screener/multibagger")
async def run_multibagger_screener_endpoint(
    top_n: int = 10,
    min_score: int = 50,
    min_market_cap: float = 1000,
    include_sectors: Optional[str] = None
):
    """
    Run the Multibagger Screener for long-term wealth creation.
    
    Identifies stocks with 2-10x return potential over 3-5 years based on:
    - Growth (25 pts): Revenue CAGR > 15%, EPS growth
    - Profitability (25 pts): ROE > 15%, margins > 10%
    - Quality (20 pts): D/E < 0.5, positive FCF, consistent earnings
    - Value (15 pts): PEG < 1.5, PE below industry
    - Moat (15 pts): Promoter > 50%, institutional interest
    
    Parameters:
    - top_n: Number of top stocks to return (default 10)
    - min_score: Minimum score 0-100 to qualify (default 50)
    - min_market_cap: Minimum market cap in Crores (default 1000)
    - include_sectors: Comma-separated sectors to focus on (optional)
    
    Returns:
    - Ranked list of multibagger candidates with investment thesis
    """
    try:
        # Get symbols to screen
        symbols = quick_screen_quality_stocks()
        
        # Add more symbols from database if available
        with db.get_connection() as conn:
            db_symbols = pd.read_sql_query(
                """
                SELECT DISTINCT symbol FROM eod 
                WHERE trade_date = (SELECT MAX(trade_date) FROM eod)
                AND symbol IN (
                    SELECT symbol FROM indicators 
                    WHERE sma_50 IS NOT NULL
                )
                LIMIT 200
                """,
                conn
            )["symbol"].tolist()
            
            # Combine with quality stocks (deduplicate)
            all_symbols = list(set(symbols + db_symbols[:50]))
        
        # Filter by sectors if specified
        if include_sectors:
            sector_list = [s.strip() for s in include_sectors.split(",")]
            all_symbols = [
                s for s in all_symbols 
                if SECTOR_MAP.get(s, "Unknown") in sector_list
            ]
        
        logger.info(f"Running multibagger screener on {len(all_symbols)} symbols...")
        
        # Run the screener
        results = run_multibagger_screener(
            symbols=all_symbols,
            top_n=top_n,
            min_score=min_score,
            min_market_cap=min_market_cap
        )
        
        return convert_to_native(results)
        
    except Exception as e:
        logger.error(f"Error running multibagger screener: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/multibagger/methodology")
async def get_multibagger_methodology_endpoint():
    """Get the multibagger screener methodology and criteria."""
    return convert_to_native(get_multibagger_methodology())


@app.get("/api/stock/{symbol}/multibagger-score")
async def get_stock_multibagger_score(symbol: str):
    """
    Get detailed multibagger score for a specific stock.
    
    Returns comprehensive fundamental analysis with:
    - Score breakdown (growth, profitability, quality, value, moat)
    - Investment thesis (pros, cons, recommendation)
    - Key metrics and target price
    """
    try:
        # Fetch fundamentals
        fundamentals = fetch_stock_fundamentals(symbol.upper())
        
        if "error" in fundamentals:
            raise HTTPException(status_code=404, detail=fundamentals["message"])
        
        # Calculate score
        score_result = calculate_multibagger_score(fundamentals)
        
        # Generate investment thesis
        from app.multibagger_screener import generate_investment_thesis
        thesis = generate_investment_thesis(fundamentals, score_result)
        
        return convert_to_native({
            "symbol": symbol.upper(),
            "company_name": fundamentals.get("company_name"),
            "sector": fundamentals.get("sector"),
            "current_price": fundamentals.get("current_price"),
            "market_cap_cr": round((fundamentals.get("market_cap", 0) or 0) / 1e7, 0),
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
            },
            "investment_thesis": thesis
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting multibagger score for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== FUTURISTIC SECTORS ENDPOINTS ==============

@app.get("/api/futuristic-sectors")
async def get_futuristic_sectors():
    """
    Get all futuristic/emerging sectors with metadata.
    
    Returns high-growth sectors expected to outperform over 5-10 years:
    - EV & Green Energy
    - AI & Data Technology
    - Defence & Aerospace
    - Digital Commerce & Fintech
    - Healthcare & Diagnostics
    - Infrastructure & Logistics
    """
    try:
        sectors = []
        
        for sector_name, data in FUTURISTIC_SECTORS.items():
            sectors.append({
                "name": sector_name,
                "description": data["description"],
                "stock_count": len(data["stocks"]),
                "top_picks": data["top_picks"],
                "growth_potential": data["growth_potential"],
                "tailwinds": data["tailwinds"][:3],  # Top 3 tailwinds
                "key_metrics": data.get("key_metrics", {})
            })
        
        return convert_to_native({
            "sectors": sectors,
            "total_sectors": len(sectors),
            "purpose": "High-growth sectors for long-term wealth creation",
            "time_horizon": "5-10 years"
        })
        
    except Exception as e:
        logger.error(f"Error getting futuristic sectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/futuristic-sectors/{sector_name}/picks")
async def get_futuristic_sector_picks(
    sector_name: str,
    top_n: int = 3
):
    """
    Get top stock picks for a futuristic sector with detailed analysis.
    
    Parameters:
    - sector_name: Name of the futuristic sector (e.g., "EV & Green Energy")
    - top_n: Number of top picks to return (default 3)
    
    Returns:
    - Top stocks with current price, fundamentals, and buy zone
    """
    try:
        # Find the sector (case-insensitive)
        sector_data = None
        actual_name = None
        
        for name, data in FUTURISTIC_SECTORS.items():
            if name.lower() == sector_name.lower() or \
               name.lower().replace(" & ", " ").replace("&", "") == sector_name.lower().replace(" & ", " ").replace("&", ""):
                sector_data = data
                actual_name = name
                break
        
        if not sector_data:
            available = list(FUTURISTIC_SECTORS.keys())
            raise HTTPException(
                status_code=404, 
                detail=f"Sector '{sector_name}' not found. Available: {available}"
            )
        
        # Get top picks
        top_picks = sector_data["top_picks"][:top_n]
        picks_with_data = []
        
        for symbol in top_picks:
            try:
                # Fetch fundamentals
                fundamentals = fetch_stock_fundamentals(symbol)
                
                if "error" in fundamentals:
                    picks_with_data.append({
                        "symbol": symbol,
                        "error": "Could not fetch data"
                    })
                    continue
                
                # Calculate score
                score_result = calculate_multibagger_score(fundamentals)
                
                # Calculate buy zone (simple model)
                current_price = fundamentals.get("current_price", 0)
                high_52w = fundamentals.get("52_week_high", current_price)
                low_52w = fundamentals.get("52_week_low", current_price * 0.8)
                
                buy_zone_low = low_52w + (high_52w - low_52w) * 0.2
                buy_zone_high = low_52w + (high_52w - low_52w) * 0.5
                
                picks_with_data.append({
                    "symbol": symbol,
                    "company_name": fundamentals.get("company_name", symbol),
                    "current_price": current_price,
                    "market_cap_cr": round((fundamentals.get("market_cap", 0) or 0) / 1e7, 0),
                    "score": score_result["total_score"],
                    "signal": score_result["signal"],
                    "metrics": {
                        "roe": fundamentals.get("roe"),
                        "revenue_growth": fundamentals.get("revenue_growth"),
                        "pe_ratio": fundamentals.get("pe_ratio"),
                        "debt_to_equity": fundamentals.get("debt_to_equity"),
                    },
                    "buy_zone": {
                        "low": round(buy_zone_low, 2),
                        "high": round(buy_zone_high, 2),
                        "current_vs_zone": "IN ZONE" if buy_zone_low <= current_price <= buy_zone_high 
                                          else "BELOW ZONE" if current_price < buy_zone_low 
                                          else "ABOVE ZONE"
                    },
                    "52_week_high": high_52w,
                    "52_week_low": low_52w,
                    "from_52w_high": fundamentals.get("from_52w_high")
                })
                
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                picks_with_data.append({
                    "symbol": symbol,
                    "error": str(e)
                })
        
        return convert_to_native({
            "sector": actual_name,
            "description": sector_data["description"],
            "growth_potential": sector_data["growth_potential"],
            "tailwinds": sector_data["tailwinds"],
            "risks": sector_data.get("risks", []),
            "key_metrics": sector_data.get("key_metrics", {}),
            "top_picks": picks_with_data,
            "all_stocks": sector_data["stocks"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting futuristic sector picks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/futuristic-sectors/summary")
async def get_futuristic_sectors_summary():
    """
    Get a quick summary of all futuristic sectors with their top pick.
    Good for dashboard overview.
    """
    try:
        summary = []
        
        for sector_name, data in FUTURISTIC_SECTORS.items():
            top_pick = data["top_picks"][0] if data["top_picks"] else None
            
            summary.append({
                "sector": sector_name,
                "description": data["description"][:100] + "...",
                "growth_potential": data["growth_potential"],
                "top_pick": top_pick,
                "stock_count": len(data["stocks"]),
                "primary_tailwind": data["tailwinds"][0] if data["tailwinds"] else None
            })
        
        return convert_to_native({
            "sectors": summary,
            "investment_horizon": "5-10 years",
            "strategy": "Long-term wealth creation through emerging themes"
        })
        
    except Exception as e:
        logger.error(f"Error getting futuristic sectors summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-performance")
async def get_sector_performance_by_period():
    """
    Get sector performance across multiple time periods (1d, 2d, 5d, 7d, 1m).
    Shows which sectors are green/red in each period with stocks in each sector.
    """
    try:
        with db.get_connection() as conn:
            # Get all historical data
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.close, e.prev_close, e.volume
                FROM eod e
                ORDER BY e.trade_date DESC
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Get unique dates sorted descending
        dates = sorted(df["trade_date"].unique(), reverse=True)
        if len(dates) < 2:
            raise HTTPException(status_code=404, detail="Not enough historical data")

        latest_date = dates[0]

        # Define periods
        periods = {
            "1d": 1,
            "2d": 2,
            "5d": 5,
            "7d": 7,
            "1m": 22  # Approx trading days in a month
        }

        # Get latest prices for each symbol
        latest_df = df[df["trade_date"] == latest_date].copy()

        # For each symbol, get historical closes
        symbol_history = {}
        for symbol in latest_df["symbol"].unique():
            symbol_data = df[df["symbol"] == symbol].sort_values("trade_date", ascending=False)
            closes = symbol_data["close"].values
            symbol_history[symbol] = closes

        # Calculate returns for each period
        sector_performance = {}
        all_sectors = [s for s in df["sector"].unique() if s != "Unknown"]

        for sector in all_sectors:
            sector_stocks = latest_df[latest_df["sector"] == sector]
            sector_symbols = sector_stocks["symbol"].tolist()

            sector_performance[sector] = {
                "sector": sector,
                "stock_count": len(sector_symbols),
                "periods": {},
                "stocks": []
            }

            # Calculate performance for each period
            for period_name, days in periods.items():
                returns = []
                for symbol in sector_symbols:
                    if symbol in symbol_history:
                        closes = symbol_history[symbol]
                        if len(closes) > days:
                            current = closes[0]
                            past = closes[days]
                            if past > 0:
                                ret = ((current - past) / past) * 100
                                returns.append(ret)

                if returns:
                    avg_return = np.mean(returns)
                    positive_count = sum(1 for r in returns if r > 0)
                    sector_performance[sector]["periods"][period_name] = {
                        "return_pct": round(float(avg_return), 2),
                        "is_positive": avg_return > 0,
                        "positive_stocks": positive_count,
                        "total_stocks": len(returns),
                        "breadth": round(float(positive_count / len(returns) * 100), 1) if returns else 0
                    }
                else:
                    sector_performance[sector]["periods"][period_name] = {
                        "return_pct": 0,
                        "is_positive": False,
                        "positive_stocks": 0,
                        "total_stocks": 0,
                        "breadth": 0
                    }

            # Add top stocks info for each sector
            stock_returns_1m = []
            for symbol in sector_symbols:
                if symbol in symbol_history:
                    closes = symbol_history[symbol]
                    if len(closes) > 22:
                        current = closes[0]
                        past = closes[22]
                        if past > 0:
                            ret = ((current - past) / past) * 100
                            stock_returns_1m.append({
                                "symbol": symbol,
                                "close": round(float(current), 2),
                                "return_1m": round(float(ret), 2),
                                "return_1d": round(float(((closes[0] - closes[1]) / closes[1]) * 100), 2) if len(closes) > 1 and closes[1] > 0 else 0
                            })

            # Sort by 1m return
            stock_returns_1m.sort(key=lambda x: x["return_1m"], reverse=True)
            sector_performance[sector]["stocks"] = stock_returns_1m[:10]  # Top 10 stocks

        # Sort sectors by 1m performance
        sorted_sectors = sorted(
            sector_performance.values(),
            key=lambda x: x["periods"].get("1m", {}).get("return_pct", 0),
            reverse=True
        )

        # Categorize sectors
        green_sectors = [s for s in sorted_sectors if s["periods"].get("1m", {}).get("is_positive", False)]
        red_sectors = [s for s in sorted_sectors if not s["periods"].get("1m", {}).get("is_positive", False)]

        return convert_to_native({
            "date": latest_date,
            "periods_available": list(periods.keys()),
            "total_sectors": len(all_sectors),
            "green_count": len(green_sectors),
            "red_count": len(red_sectors),
            "sectors": sorted_sectors,
            "green_sectors": [s["sector"] for s in green_sectors],
            "red_sectors": [s["sector"] for s in red_sectors]
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sector performance: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector/{sector_name}/performance")
async def get_single_sector_performance(sector_name: str):
    """
    Get detailed performance for a specific sector with all stocks.
    """
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.close, e.prev_close, e.volume,
                       i.rsi_14, i.sma_20, i.sma_50
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.trade_date DESC
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Filter by sector
        sector_df = df[df["sector"].str.lower() == sector_name.lower()]

        if sector_df.empty:
            raise HTTPException(status_code=404, detail=f"Sector '{sector_name}' not found")

        # Get unique dates
        dates = sorted(sector_df["trade_date"].unique(), reverse=True)
        latest_date = dates[0]

        # Periods
        periods = {"1d": 1, "2d": 2, "5d": 5, "7d": 7, "1m": 22}

        # Get all stocks in sector
        symbols = sector_df[sector_df["trade_date"] == latest_date]["symbol"].unique()

        stocks = []
        for symbol in symbols:
            symbol_data = sector_df[sector_df["symbol"] == symbol].sort_values("trade_date", ascending=False)
            if symbol_data.empty:
                continue

            latest = symbol_data.iloc[0]
            closes = symbol_data["close"].values

            stock_info = {
                "symbol": symbol,
                "close": round(float(latest["close"]), 2),
                "rsi": round(float(latest["rsi_14"]), 1) if pd.notna(latest.get("rsi_14")) else None,
                "above_sma20": bool(latest["close"] > latest.get("sma_20", 0)) if pd.notna(latest.get("sma_20")) else None,
                "above_sma50": bool(latest["close"] > latest.get("sma_50", 0)) if pd.notna(latest.get("sma_50")) else None,
                "returns": {}
            }

            # Calculate returns for each period
            for period_name, days in periods.items():
                if len(closes) > days and closes[days] > 0:
                    ret = ((closes[0] - closes[days]) / closes[days]) * 100
                    stock_info["returns"][period_name] = round(float(ret), 2)
                else:
                    stock_info["returns"][period_name] = None

            stocks.append(stock_info)

        # Sort by 1m return
        stocks.sort(key=lambda x: x["returns"].get("1m", 0) or 0, reverse=True)

        # Calculate sector average returns
        sector_returns = {}
        for period_name in periods.keys():
            rets = [s["returns"].get(period_name) for s in stocks if s["returns"].get(period_name) is not None]
            if rets:
                sector_returns[period_name] = {
                    "avg_return": round(float(np.mean(rets)), 2),
                    "is_positive": np.mean(rets) > 0,
                    "positive_count": sum(1 for r in rets if r > 0),
                    "total_count": len(rets)
                }
            else:
                sector_returns[period_name] = {"avg_return": 0, "is_positive": False, "positive_count": 0, "total_count": 0}

        sector_info = SECTOR_INFO.get(sector_name, SECTOR_INFO.get("Unknown", {}))

        return convert_to_native({
            "sector": sector_name,
            "sector_info": sector_info,
            "date": latest_date,
            "total_stocks": len(stocks),
            "sector_returns": sector_returns,
            "stocks": stocks
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sector performance: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/patterns")
async def get_stock_patterns(symbol: str):
    """Get pattern analysis for a specific stock"""
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, i.sma_20, i.sma_50, i.rsi_14, i.atr_14
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.symbol = ?
                ORDER BY e.trade_date
                """,
                conn,
                params=(symbol,)
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        # Calculate patterns
        df = calculate_pattern_score(df)
        df = calculate_trend_strength(df)

        latest = df.iloc[-1]

        # Get recent patterns (last 10 days)
        recent = df.tail(10)

        recent_patterns = []
        for _, row in recent.iterrows():
            patterns = []
            if row.get('pattern_bullish_engulfing', False):
                patterns.append("Bullish Engulfing")
            if row.get('pattern_hammer', False):
                patterns.append("Hammer")
            if row.get('pattern_morning_star', False):
                patterns.append("Morning Star")
            if row.get('pattern_three_white_soldiers', False):
                patterns.append("Three White Soldiers")
            if row.get('pattern_consolidation_breakout', False):
                patterns.append("Consolidation Breakout")

            if patterns:
                recent_patterns.append({
                    "date": row["trade_date"],
                    "patterns": patterns,
                    "score": int(row.get("pattern_score", 0))
                })

        return {
            "symbol": symbol,
            "latest_date": latest["trade_date"],
            "current_price": float(latest["close"]),
            "pattern_analysis": {
                "pattern_score": int(latest.get("pattern_score", 0)),
                "patterns_detected": get_pattern_summary(latest),
                "trend_strength": int(latest.get("trend_strength", 0)),
                "adx": round(float(latest.get("adx", 0)), 1) if pd.notna(latest.get("adx")) else 0,
                "supertrend_direction": "BULLISH" if latest.get("supertrend_direction", 0) == 1 else "BEARISH",
                "ma_aligned": int(latest.get("ma_aligned", 0)),
            },
            "recent_patterns": recent_patterns,
            "interpretation": {
                "pattern_strength": "STRONG" if latest.get("pattern_score", 0) >= 5 else
                                   "MODERATE" if latest.get("pattern_score", 0) >= 3 else "WEAK",
                "trend": "STRONG UPTREND" if latest.get("trend_strength", 0) >= 7 else
                        "UPTREND" if latest.get("trend_strength", 0) >= 4 else
                        "NEUTRAL" if latest.get("trend_strength", 0) >= 2 else "DOWNTREND",
                "recommendation": "STRONG BUY" if latest.get("pattern_score", 0) >= 5 and latest.get("trend_strength", 0) >= 7 else
                                 "BUY" if latest.get("pattern_score", 0) >= 3 and latest.get("trend_strength", 0) >= 4 else
                                 "HOLD" if latest.get("trend_strength", 0) >= 2 else "AVOID"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stock patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SECTOR SEASONALITY HEATMAP ENDPOINTS ====================

@app.get("/api/seasonality/heatmap")
async def get_seasonality_heatmap():
    """
    Get sector seasonality heatmap based on 10 years of historical data.
    Shows which sectors perform best in which months.
    """
    try:
        with db.get_connection() as conn:
            # Get all historical EOD data
            df = pd.read_sql_query(
                """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM eod
                ORDER BY symbol, trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Filter out Unknown sector
        df = df[df["sector"] != "Unknown"]

        logger.info(f"Calculating seasonality for {df['symbol'].nunique()} stocks across {df['sector'].nunique()} sectors")

        # Calculate seasonality heatmap
        heatmap_data = calculate_sector_seasonality(df)

        # Get list of sectors and months for frontend
        sectors = sorted(heatmap_data.keys())

        return convert_to_native({
            "sectors": sectors,
            "months": MONTH_NAMES,
            "heatmap": heatmap_data,
            "data_info": {
                "total_stocks": df["symbol"].nunique(),
                "total_sectors": len(sectors),
                "date_range": {
                    "start": df["trade_date"].min(),
                    "end": df["trade_date"].max()
                }
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating seasonality heatmap: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasonality/recommendations")
async def get_seasonality_recommendations(month: int = None):
    """
    Get sector and stock recommendations for a specific month (or current month).
    Based on historical seasonality analysis.
    """
    try:
        from datetime import datetime as dt

        # Use current month if not specified
        if month is None:
            month = dt.now().month

        if not 1 <= month <= 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM eod
                ORDER BY symbol, trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        df = df[df["sector"] != "Unknown"]

        # Get top sectors for the month
        top_sectors = get_top_sectors_for_month(df, month, top_n=3)

        # Get top stocks for each sector
        sector_stocks = {}
        for sector_info in top_sectors:
            sector_name = sector_info["sector"]
            stocks = get_top_stocks_in_sector(df, sector_name, top_n=3)
            sector_stocks[sector_name] = stocks

        return convert_to_native({
            "month": MONTH_NAMES[month - 1],
            "month_number": month,
            "top_sectors": top_sectors,
            "sector_stocks": sector_stocks,
            "recommendation_summary": f"Based on 10 years of data, {', '.join([s['sector'] for s in top_sectors])} historically perform best in {MONTH_NAMES[month - 1]}"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting seasonality recommendations: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasonality/sector/{sector_name}/stocks")
async def get_seasonality_sector_stocks(sector_name: str, top_n: int = 5, include_financials: bool = False):
    """
    Get top performing stocks within a sector based on historical performance.
    Includes undervalued identification and optionally financial data.
    Only returns stocks with current (non-stale) data.
    """
    try:
        with db.get_connection() as conn:
            # First get the latest date in the database
            latest_date = pd.read_sql_query("SELECT MAX(trade_date) as max_date FROM eod", conn).iloc[0]['max_date']
            
            # Get symbols that have data on the latest date (fresh stocks only)
            fresh_symbols = pd.read_sql_query(
                "SELECT DISTINCT symbol FROM eod WHERE trade_date = ?", 
                conn, 
                params=[latest_date]
            )['symbol'].tolist()
            
            df = pd.read_sql_query(
                """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM eod
                ORDER BY symbol, trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        # Filter to only include fresh stocks
        df = df[df["symbol"].isin(fresh_symbols)]
        
        if df.empty:
            raise HTTPException(status_code=404, detail="No stocks with current data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Check if sector exists
        available_sectors = df["sector"].unique()
        matching_sector = None
        for s in available_sectors:
            if s.lower() == sector_name.lower():
                matching_sector = s
                break

        if not matching_sector:
            raise HTTPException(
                status_code=404,
                detail=f"Sector '{sector_name}' not found. Available sectors: {', '.join(sorted([s for s in available_sectors if s != 'Unknown']))}"
            )

        # Get top stocks with or without financials
        if include_financials:
            stocks = get_sector_stocks_with_financials(df, matching_sector, top_n=top_n)
        else:
            stocks = get_top_stocks_in_sector(df, matching_sector, top_n=top_n)

        return convert_to_native({
            "sector": matching_sector,
            "stocks": stocks,
            "total_stocks_in_sector": df[df["sector"] == matching_sector]["symbol"].nunique(),
            "criteria": "Stocks ranked by: CAGR (35%), Sharpe ratio (25%), Win rate (20%), Value score (20%)",
            "include_financials": include_financials
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sector stocks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasonality/stock/{symbol}/financials")
async def get_stock_financials(symbol: str):
    """
    Get detailed financial data for a specific stock.
    Includes PE, PB, ROE, dividend yield, and other fundamentals.
    """
    try:
        from app.sector_seasonality import fetch_financial_data

        financials = fetch_financial_data(symbol)

        if "error" in financials:
            raise HTTPException(status_code=404, detail=f"Could not fetch financials for {symbol}: {financials['error']}")

        return convert_to_native(financials)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stock financials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasonality/validate")
async def validate_seasonality():
    """
    Validate seasonality statistics to ensure data quality.
    Runs sanity checks on the historical data.
    """
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM eod
                ORDER BY symbol, trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        df = df[df["sector"] != "Unknown"]

        # Run validation
        validation_results = validate_seasonality_stats(df)

        # Calculate overall pass/fail
        all_checks_passed = all(check["passed"] for check in validation_results["sanity_checks"])
        validation_results["overall_status"] = "VALID" if all_checks_passed else "NEEDS REVIEW"

        return convert_to_native(validation_results)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating seasonality: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasonality/month-vs-month")
async def get_month_comparison():
    """
    Compare all sectors across all months to find the best month for each sector.
    Returns a matrix of sector x month with rankings.
    """
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM eod
                ORDER BY symbol, trade_date
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        df = df[df["sector"] != "Unknown"]

        # Get heatmap data
        heatmap_data = calculate_sector_seasonality(df)

        # Find best months for each sector
        sector_best_months = []
        for sector, monthly_data in heatmap_data.items():
            # Sort months by average return
            month_returns = [(month, data["avg_return"]) for month, data in monthly_data.items()]
            month_returns.sort(key=lambda x: x[1], reverse=True)

            best_months = month_returns[:3]  # Top 3 months
            worst_months = month_returns[-2:]  # Bottom 2 months

            sector_best_months.append({
                "sector": sector,
                "best_months": [{"month": m, "avg_return": r} for m, r in best_months],
                "worst_months": [{"month": m, "avg_return": r} for m, r in worst_months],
                "yearly_avg": round(sum(r for _, r in month_returns) / len(month_returns), 2)
            })

        # Sort by yearly average
        sector_best_months.sort(key=lambda x: x["yearly_avg"], reverse=True)

        # Find best sector for each month
        month_best_sectors = {}
        for month in MONTH_NAMES:
            sectors_for_month = []
            for sector, monthly_data in heatmap_data.items():
                if month in monthly_data:
                    sectors_for_month.append({
                        "sector": sector,
                        "avg_return": monthly_data[month]["avg_return"],
                        "win_rate": monthly_data[month]["win_rate"]
                    })

            sectors_for_month.sort(key=lambda x: x["avg_return"], reverse=True)
            month_best_sectors[month] = sectors_for_month[:3]  # Top 3 sectors for each month

        return convert_to_native({
            "sector_analysis": sector_best_months,
            "month_analysis": month_best_sectors,
            "insights": {
                "best_overall_sector": sector_best_months[0]["sector"] if sector_best_months else None,
                "worst_overall_sector": sector_best_months[-1]["sector"] if sector_best_months else None,
                "total_sectors_analyzed": len(sector_best_months)
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting month comparison: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== NEWS & ANNOUNCEMENTS ENDPOINTS ====================

@app.get("/api/news/latest")
async def get_latest_news(force_refresh: bool = False, days: int = 3):
    """
    Get latest news and corporate announcements from NSE.
    Includes sentiment analysis and trading signals.

    Parameters:
    - force_refresh: Force fetch new data (default: use cache)
    - days: Number of days to look back (default: 3)
    """
    try:
        aggregator = get_news_aggregator()
        news_data = aggregator.get_latest_news(force_refresh=force_refresh, days=days)

        return convert_to_native({
            "status": "success",
            "news": news_data.get("news", []),
            "summary": news_data.get("summary", {}),
            "last_updated": news_data.get("last_updated", "")
        })

    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/signals")
async def get_news_signals(min_confidence: float = 50):
    """
    Get actionable trading signals from news analysis.
    Only returns high-confidence BUY/SELL signals.

    Parameters:
    - min_confidence: Minimum confidence score (0-100, default: 50)
    """
    try:
        aggregator = get_news_aggregator()
        signals = aggregator.get_actionable_signals(min_confidence=min_confidence)

        # Group by signal type
        buy_signals = [s for s in signals if s["signal"] in ["STRONG_BUY", "BUY"]]
        sell_signals = [s for s in signals if s["signal"] in ["STRONG_SELL", "SELL"]]

        return convert_to_native({
            "status": "success",
            "total_signals": len(signals),
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "summary": {
                "strong_buy_count": sum(1 for s in signals if s["signal"] == "STRONG_BUY"),
                "buy_count": sum(1 for s in signals if s["signal"] == "BUY"),
                "sell_count": sum(1 for s in signals if s["signal"] == "SELL"),
                "strong_sell_count": sum(1 for s in signals if s["signal"] == "STRONG_SELL")
            }
        })

    except Exception as e:
        logger.error(f"Error fetching news signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/symbol/{symbol}")
async def get_news_for_symbol(symbol: str):
    """
    Get all news and signals for a specific stock symbol.
    """
    try:
        aggregator = get_news_aggregator()
        signals = aggregator.get_signals_for_symbol(symbol.upper())

        if not signals:
            return {
                "status": "success",
                "symbol": symbol.upper(),
                "news": [],
                "message": "No recent news found for this symbol"
            }

        # Sort by timestamp
        signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Calculate overall sentiment
        buy_count = sum(1 for s in signals if s["signal"] in ["STRONG_BUY", "BUY"])
        sell_count = sum(1 for s in signals if s["signal"] in ["STRONG_SELL", "SELL"])

        if buy_count > sell_count:
            overall_sentiment = "BULLISH"
        elif sell_count > buy_count:
            overall_sentiment = "BEARISH"
        else:
            overall_sentiment = "NEUTRAL"

        return convert_to_native({
            "status": "success",
            "symbol": symbol.upper(),
            "news": signals,
            "overall_sentiment": overall_sentiment,
            "signal_counts": {
                "bullish": buy_count,
                "bearish": sell_count,
                "neutral": len(signals) - buy_count - sell_count
            }
        })

    except Exception as e:
        logger.error(f"Error fetching news for symbol: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/refresh")
async def refresh_news():
    """
    Force refresh news data from NSE.
    Use this to manually trigger a refresh.
    """
    try:
        aggregator = get_news_aggregator()
        news_data = aggregator.get_latest_news(force_refresh=True, days=7)

        return convert_to_native({
            "status": "success",
            "message": "News refreshed successfully",
            "news_count": len(news_data.get("news", [])),
            "summary": news_data.get("summary", {}),
            "last_updated": news_data.get("last_updated", "")
        })

    except Exception as e:
        logger.error(f"Error refreshing news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SECTOR VALUATION ENDPOINTS ====================

@app.get("/api/sector-valuation")
async def get_sector_valuation_analysis():
    """
    Get undervalued and overvalued stocks for each sector.
    Valuation based on:
    - Distance from 52-week high (undervalued if >20% below high)
    - RSI levels (oversold <35 = undervalued, overbought >70 = overvalued)
    - Price vs 200 SMA (below = potentially undervalued)
    - Recent momentum
    """
    try:
        with db.get_connection() as conn:
            # Get all historical data for analysis
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.symbol, e.trade_date DESC
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        df = df[df["sector"] != "Unknown"]

        # Get unique dates and latest date
        latest_date = df["trade_date"].max()

        # Calculate 52-week high for each symbol
        symbol_metrics = {}
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("trade_date", ascending=False)

            # Get latest data
            latest = group.iloc[0]

            # Calculate 52-week (252 trading days) metrics
            hist_data = group.head(252)  # Last ~1 year
            if len(hist_data) < 50:  # Need at least 50 days of data
                continue

            high_52w = hist_data["high"].max()
            low_52w = hist_data["low"].min()
            current_price = latest["close"]

            # Distance from 52-week high (percentage below)
            dist_from_high = ((high_52w - current_price) / high_52w) * 100 if high_52w > 0 else 0

            # Distance from 52-week low (percentage above)
            dist_from_low = ((current_price - low_52w) / low_52w) * 100 if low_52w > 0 else 0

            # Calculate 200 SMA if we have enough data
            if len(hist_data) >= 200:
                sma_200 = hist_data.head(200)["close"].mean()
            else:
                sma_200 = hist_data["close"].mean()

            # Price relative to 200 SMA
            price_vs_sma200 = ((current_price - sma_200) / sma_200) * 100 if sma_200 > 0 else 0

            # RSI
            rsi = latest.get("rsi_14", 50)
            if pd.isna(rsi):
                rsi = 50

            # Volume ratio (current vs average)
            vol_ma = latest.get("vol_ma_20", 0)
            vol_ratio = latest["volume"] / vol_ma if vol_ma and vol_ma > 0 else 1

            # Calculate valuation score (-100 to +100)
            # Negative = undervalued, Positive = overvalued
            valuation_score = 0

            # Distance from 52w high contribution (-40 to 0)
            if dist_from_high > 40:
                valuation_score -= 40  # Very undervalued
            elif dist_from_high > 25:
                valuation_score -= 25
            elif dist_from_high > 15:
                valuation_score -= 15
            elif dist_from_high > 5:
                valuation_score -= 5
            else:
                valuation_score += 10  # Near high = fair/overvalued

            # RSI contribution (-30 to +30)
            if rsi < 30:
                valuation_score -= 30  # Oversold
            elif rsi < 40:
                valuation_score -= 15
            elif rsi > 75:
                valuation_score += 30  # Overbought
            elif rsi > 65:
                valuation_score += 15

            # Price vs 200 SMA contribution (-20 to +20)
            if price_vs_sma200 < -15:
                valuation_score -= 20  # Well below SMA
            elif price_vs_sma200 < -5:
                valuation_score -= 10
            elif price_vs_sma200 > 20:
                valuation_score += 20  # Well above SMA
            elif price_vs_sma200 > 10:
                valuation_score += 10

            # Determine valuation category
            if valuation_score <= -40:
                valuation = "DEEPLY_UNDERVALUED"
            elif valuation_score <= -20:
                valuation = "UNDERVALUED"
            elif valuation_score <= 10:
                valuation = "FAIR_VALUE"
            elif valuation_score <= 30:
                valuation = "OVERVALUED"
            else:
                valuation = "DEEPLY_OVERVALUED"

            symbol_metrics[symbol] = {
                "symbol": symbol,
                "sector": latest["sector"],
                "close": round(float(current_price), 2),
                "high_52w": round(float(high_52w), 2),
                "low_52w": round(float(low_52w), 2),
                "dist_from_high_pct": round(float(dist_from_high), 1),
                "dist_from_low_pct": round(float(dist_from_low), 1),
                "rsi": round(float(rsi), 1),
                "sma_200": round(float(sma_200), 2),
                "price_vs_sma200_pct": round(float(price_vs_sma200), 1),
                "vol_ratio": round(float(vol_ratio), 2),
                "valuation_score": int(valuation_score),
                "valuation": valuation
            }

        # Group by sector
        sector_valuation = {}
        for symbol, metrics in symbol_metrics.items():
            sector = metrics["sector"]
            if sector not in sector_valuation:
                sector_valuation[sector] = {
                    "sector": sector,
                    "undervalued": [],
                    "fair_value": [],
                    "overvalued": [],
                    "summary": {}
                }

            if metrics["valuation"] in ["DEEPLY_UNDERVALUED", "UNDERVALUED"]:
                sector_valuation[sector]["undervalued"].append(metrics)
            elif metrics["valuation"] in ["DEEPLY_OVERVALUED", "OVERVALUED"]:
                sector_valuation[sector]["overvalued"].append(metrics)
            else:
                sector_valuation[sector]["fair_value"].append(metrics)

        # Sort stocks within each category and add summary
        for sector, data in sector_valuation.items():
            # Sort undervalued by score (most undervalued first)
            data["undervalued"].sort(key=lambda x: x["valuation_score"])
            data["undervalued"] = data["undervalued"][:10]  # Top 10

            # Sort overvalued by score (most overvalued first)
            data["overvalued"].sort(key=lambda x: x["valuation_score"], reverse=True)
            data["overvalued"] = data["overvalued"][:10]  # Top 10

            # Fair value - sort by distance from high
            data["fair_value"].sort(key=lambda x: x["dist_from_high_pct"], reverse=True)
            data["fair_value"] = data["fair_value"][:5]  # Top 5

            # Summary
            total = len([s for s, m in symbol_metrics.items() if m["sector"] == sector])
            data["summary"] = {
                "total_stocks": total,
                "undervalued_count": len([s for s, m in symbol_metrics.items()
                                         if m["sector"] == sector and m["valuation"] in ["DEEPLY_UNDERVALUED", "UNDERVALUED"]]),
                "fair_value_count": len([s for s, m in symbol_metrics.items()
                                        if m["sector"] == sector and m["valuation"] == "FAIR_VALUE"]),
                "overvalued_count": len([s for s, m in symbol_metrics.items()
                                        if m["sector"] == sector and m["valuation"] in ["DEEPLY_OVERVALUED", "OVERVALUED"]])
            }

        # Sort sectors by number of undervalued stocks
        sorted_sectors = sorted(
            sector_valuation.values(),
            key=lambda x: len(x["undervalued"]),
            reverse=True
        )

        # Get overall market summary
        all_undervalued = sum(s["summary"]["undervalued_count"] for s in sorted_sectors)
        all_overvalued = sum(s["summary"]["overvalued_count"] for s in sorted_sectors)
        all_fair = sum(s["summary"]["fair_value_count"] for s in sorted_sectors)

        return convert_to_native({
            "date": latest_date,
            "market_summary": {
                "total_stocks_analyzed": len(symbol_metrics),
                "undervalued_count": all_undervalued,
                "fair_value_count": all_fair,
                "overvalued_count": all_overvalued,
                "market_sentiment": "FEARFUL" if all_undervalued > all_overvalued * 1.5 else
                                   "GREEDY" if all_overvalued > all_undervalued * 1.5 else "NEUTRAL"
            },
            "sectors": sorted_sectors,
            "methodology": {
                "factors": [
                    "Distance from 52-week high (40% weight)",
                    "RSI oversold/overbought levels (30% weight)",
                    "Price vs 200-day SMA (20% weight)",
                    "Volume analysis (10% weight)"
                ],
                "undervalued_criteria": "Valuation score <= -20 (lower = more undervalued)",
                "overvalued_criteria": "Valuation score >= 20 (higher = more overvalued)"
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sector valuation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector/{sector_name}/valuation")
async def get_single_sector_valuation(sector_name: str):
    """
    Get detailed undervalued/overvalued stocks for a specific sector.
    """
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.symbol, e.trade_date DESC
                """,
                conn
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Add sector information
        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")

        # Find matching sector
        available_sectors = df["sector"].unique()
        matching_sector = None
        for s in available_sectors:
            if s.lower() == sector_name.lower():
                matching_sector = s
                break

        if not matching_sector:
            raise HTTPException(
                status_code=404,
                detail=f"Sector '{sector_name}' not found. Available: {', '.join(sorted([s for s in available_sectors if s != 'Unknown']))}"
            )

        # Filter to sector
        sector_df = df[df["sector"] == matching_sector]
        latest_date = sector_df["trade_date"].max()

        # Calculate metrics for each stock
        stocks = []
        for symbol, group in sector_df.groupby("symbol"):
            group = group.sort_values("trade_date", ascending=False)
            latest = group.iloc[0]

            # 52-week data
            hist_data = group.head(252)
            if len(hist_data) < 30:
                continue

            high_52w = hist_data["high"].max()
            low_52w = hist_data["low"].min()
            current_price = latest["close"]

            dist_from_high = ((high_52w - current_price) / high_52w) * 100 if high_52w > 0 else 0

            # 200 SMA
            sma_200 = hist_data.head(200)["close"].mean() if len(hist_data) >= 200 else hist_data["close"].mean()
            price_vs_sma200 = ((current_price - sma_200) / sma_200) * 100 if sma_200 > 0 else 0

            rsi = latest.get("rsi_14", 50)
            if pd.isna(rsi):
                rsi = 50

            # Valuation score
            valuation_score = 0

            if dist_from_high > 40:
                valuation_score -= 40
            elif dist_from_high > 25:
                valuation_score -= 25
            elif dist_from_high > 15:
                valuation_score -= 15
            elif dist_from_high > 5:
                valuation_score -= 5
            else:
                valuation_score += 10

            if rsi < 30:
                valuation_score -= 30
            elif rsi < 40:
                valuation_score -= 15
            elif rsi > 75:
                valuation_score += 30
            elif rsi > 65:
                valuation_score += 15

            if price_vs_sma200 < -15:
                valuation_score -= 20
            elif price_vs_sma200 < -5:
                valuation_score -= 10
            elif price_vs_sma200 > 20:
                valuation_score += 20
            elif price_vs_sma200 > 10:
                valuation_score += 10

            if valuation_score <= -40:
                valuation = "DEEPLY_UNDERVALUED"
            elif valuation_score <= -20:
                valuation = "UNDERVALUED"
            elif valuation_score <= 10:
                valuation = "FAIR_VALUE"
            elif valuation_score <= 30:
                valuation = "OVERVALUED"
            else:
                valuation = "DEEPLY_OVERVALUED"

            stocks.append({
                "symbol": symbol,
                "close": round(float(current_price), 2),
                "high_52w": round(float(high_52w), 2),
                "low_52w": round(float(low_52w), 2),
                "dist_from_high_pct": round(float(dist_from_high), 1),
                "rsi": round(float(rsi), 1),
                "sma_200": round(float(sma_200), 2),
                "price_vs_sma200_pct": round(float(price_vs_sma200), 1),
                "valuation_score": int(valuation_score),
                "valuation": valuation
            })

        # Sort by valuation score
        stocks.sort(key=lambda x: x["valuation_score"])

        undervalued = [s for s in stocks if s["valuation"] in ["DEEPLY_UNDERVALUED", "UNDERVALUED"]]
        overvalued = [s for s in stocks if s["valuation"] in ["DEEPLY_OVERVALUED", "OVERVALUED"]]
        fair_value = [s for s in stocks if s["valuation"] == "FAIR_VALUE"]

        return convert_to_native({
            "sector": matching_sector,
            "date": latest_date,
            "total_stocks": len(stocks),
            "summary": {
                "undervalued_count": len(undervalued),
                "fair_value_count": len(fair_value),
                "overvalued_count": len(overvalued)
            },
            "undervalued": undervalued,
            "fair_value": fair_value[:10],  # Limit to 10
            "overvalued": list(reversed(overvalued)),  # Most overvalued first
            "recommendation": f"Found {len(undervalued)} undervalued stocks in {matching_sector}. "
                            f"Consider these for long-term wealth building when sector rotation is favorable."
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sector valuation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SUPPORT/RESISTANCE/TARGET ENDPOINTS ====================

@app.get("/api/stock/{symbol}/levels")
async def get_stock_levels(symbol: str):
    """
    Calculate support, resistance, and target levels for a stock.
    Uses multiple methods:
    - Pivot points (classic, fibonacci)
    - Recent swing highs/lows
    - Moving averages as dynamic S/R
    - Volume profile (high volume areas)
    """
    try:
        with db.get_connection() as conn:
            # Get last 250 trading days of data
            df = pd.read_sql_query(
                """
                SELECT trade_date, open, high, low, close, volume
                FROM eod
                WHERE symbol = ?
                ORDER BY trade_date DESC
                LIMIT 250
                """,
                conn,
                params=(symbol.upper(),)
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        df = df.sort_values('trade_date').reset_index(drop=True)

        current_price = float(df['close'].iloc[-1])
        high_today = float(df['high'].iloc[-1])
        low_today = float(df['low'].iloc[-1])

        # Get recent data for calculations
        recent_20 = df.tail(20)
        recent_50 = df.tail(50)

        # ============ PIVOT POINTS (Classic) ============
        # Use previous day's HLC
        prev_high = float(df['high'].iloc[-2]) if len(df) > 1 else high_today
        prev_low = float(df['low'].iloc[-2]) if len(df) > 1 else low_today
        prev_close = float(df['close'].iloc[-2]) if len(df) > 1 else current_price

        pivot = (prev_high + prev_low + prev_close) / 3

        # Classic pivot levels
        r1 = 2 * pivot - prev_low
        r2 = pivot + (prev_high - prev_low)
        r3 = prev_high + 2 * (pivot - prev_low)

        s1 = 2 * pivot - prev_high
        s2 = pivot - (prev_high - prev_low)
        s3 = prev_low - 2 * (prev_high - pivot)

        # ============ FIBONACCI PIVOT LEVELS ============
        fib_r1 = pivot + 0.382 * (prev_high - prev_low)
        fib_r2 = pivot + 0.618 * (prev_high - prev_low)
        fib_r3 = pivot + 1.0 * (prev_high - prev_low)

        fib_s1 = pivot - 0.382 * (prev_high - prev_low)
        fib_s2 = pivot - 0.618 * (prev_high - prev_low)
        fib_s3 = pivot - 1.0 * (prev_high - prev_low)

        # ============ SWING HIGHS/LOWS (Last 20 days) ============
        swing_highs = []
        swing_lows = []

        for i in range(2, len(recent_20) - 2):
            # Swing high: higher than 2 bars on each side
            if (recent_20['high'].iloc[i] > recent_20['high'].iloc[i-1] and
                recent_20['high'].iloc[i] > recent_20['high'].iloc[i-2] and
                recent_20['high'].iloc[i] > recent_20['high'].iloc[i+1] and
                recent_20['high'].iloc[i] > recent_20['high'].iloc[i+2]):
                swing_highs.append(float(recent_20['high'].iloc[i]))

            # Swing low: lower than 2 bars on each side
            if (recent_20['low'].iloc[i] < recent_20['low'].iloc[i-1] and
                recent_20['low'].iloc[i] < recent_20['low'].iloc[i-2] and
                recent_20['low'].iloc[i] < recent_20['low'].iloc[i+1] and
                recent_20['low'].iloc[i] < recent_20['low'].iloc[i+2]):
                swing_lows.append(float(recent_20['low'].iloc[i]))

        # ============ MOVING AVERAGES (Dynamic S/R) ============
        sma_20 = float(df['close'].tail(20).mean())
        sma_50 = float(df['close'].tail(50).mean())
        sma_200 = float(df['close'].mean()) if len(df) >= 200 else float(df['close'].mean())

        # EMA calculations
        ema_9 = float(df['close'].ewm(span=9, adjust=False).mean().iloc[-1])
        ema_21 = float(df['close'].ewm(span=21, adjust=False).mean().iloc[-1])

        # ============ 52-WEEK HIGH/LOW ============
        high_52w = float(df['high'].max())
        low_52w = float(df['low'].min())

        # ============ VOLUME WEIGHTED LEVELS ============
        # Find price levels with highest volume (support/resistance zones)
        df['price_bin'] = pd.cut(df['close'], bins=20)
        volume_profile = df.groupby('price_bin')['volume'].sum().sort_values(ascending=False)

        high_volume_zones = []
        for interval in volume_profile.head(3).index:
            if pd.notna(interval):
                zone_mid = (interval.left + interval.right) / 2
                high_volume_zones.append(round(zone_mid, 2))

        # ============ CONSOLIDATE SUPPORT LEVELS ============
        all_supports = []

        # Add supports below current price
        for level in [s1, s2, s3, fib_s1, fib_s2, fib_s3, sma_20, sma_50, sma_200, ema_21, low_52w] + swing_lows + high_volume_zones:
            if level < current_price:
                all_supports.append(level)

        # Remove duplicates and sort (closest first)
        all_supports = sorted(set([round(s, 2) for s in all_supports]), reverse=True)

        # Get top 3 nearest supports
        immediate_supports = all_supports[:3] if all_supports else [round(current_price * 0.97, 2)]

        # ============ CONSOLIDATE RESISTANCE LEVELS ============
        all_resistances = []

        # Add resistances above current price
        for level in [r1, r2, r3, fib_r1, fib_r2, fib_r3, sma_20, sma_50, sma_200, ema_9, high_52w] + swing_highs + high_volume_zones:
            if level > current_price:
                all_resistances.append(level)

        # Remove duplicates and sort (closest first)
        all_resistances = sorted(set([round(r, 2) for r in all_resistances]))

        # Get top 3 nearest resistances
        immediate_resistances = all_resistances[:3] if all_resistances else [round(current_price * 1.03, 2)]

        # ============ TARGET CALCULATION ============
        # Primary target: Next resistance level
        target_1 = immediate_resistances[0] if immediate_resistances else current_price * 1.05

        # Secondary target: Based on risk-reward (2:1 from nearest support)
        stop_loss = immediate_supports[0] if immediate_supports else current_price * 0.97
        risk = current_price - stop_loss
        target_2 = current_price + (risk * 2)  # 2:1 RR
        target_3 = current_price + (risk * 3)  # 3:1 RR

        # Fibonacci extension targets
        swing_range = high_52w - low_52w
        fib_target_1 = current_price + (swing_range * 0.236)
        fib_target_2 = current_price + (swing_range * 0.382)

        # ============ SWING TRADING RECOMMENDATION ============
        # Calculate potential gain percentages
        target_1_gain = ((target_1 - current_price) / current_price) * 100
        target_2_gain = ((target_2 - current_price) / current_price) * 100
        stop_loss_risk = ((current_price - stop_loss) / current_price) * 100

        # Risk-reward ratio
        rr_ratio = target_1_gain / stop_loss_risk if stop_loss_risk > 0 else 0

        # Trend assessment
        trend = "BULLISH" if current_price > sma_50 > sma_200 else \
                "BEARISH" if current_price < sma_50 < sma_200 else "SIDEWAYS"

        # Position near support?
        near_support = any(abs(current_price - s) / current_price < 0.02 for s in immediate_supports)
        near_resistance = any(abs(r - current_price) / current_price < 0.02 for r in immediate_resistances)

        # Generate recommendation
        if near_support and trend in ["BULLISH", "SIDEWAYS"] and rr_ratio >= 2:
            recommendation = "STRONG BUY"
            reasoning = f"Price near support ({immediate_supports[0]:.2f}), good R:R ratio of {rr_ratio:.1f}:1"
        elif rr_ratio >= 2 and trend == "BULLISH":
            recommendation = "BUY"
            reasoning = f"Bullish trend with favorable R:R of {rr_ratio:.1f}:1"
        elif near_resistance:
            recommendation = "WAIT"
            reasoning = f"Price near resistance ({immediate_resistances[0]:.2f}), wait for breakout or pullback"
        elif trend == "BEARISH":
            recommendation = "AVOID"
            reasoning = "Bearish trend, wait for trend reversal"
        else:
            recommendation = "NEUTRAL"
            reasoning = "No clear setup, wait for better entry"

        return JSONResponse({
            "symbol": symbol.upper(),
            "current_price": round(current_price, 2),
            "trade_date": df['trade_date'].iloc[-1],

            "support_levels": {
                "immediate": [round(s, 2) for s in immediate_supports],
                "s1_pivot": round(s1, 2),
                "s2_pivot": round(s2, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2),
                "52w_low": round(low_52w, 2)
            },

            "resistance_levels": {
                "immediate": [round(r, 2) for r in immediate_resistances],
                "r1_pivot": round(r1, 2),
                "r2_pivot": round(r2, 2),
                "52w_high": round(high_52w, 2)
            },

            "targets": {
                "target_1": round(target_1, 2),
                "target_1_gain_pct": round(target_1_gain, 2),
                "target_2": round(target_2, 2),
                "target_2_gain_pct": round(target_2_gain, 2),
                "target_3": round(target_3, 2),
                "fibonacci_targets": [round(fib_target_1, 2), round(fib_target_2, 2)]
            },

            "stop_loss": {
                "recommended": round(stop_loss, 2),
                "risk_pct": round(stop_loss_risk, 2),
                "alternative": round(immediate_supports[1], 2) if len(immediate_supports) > 1 else round(stop_loss * 0.98, 2)
            },

            "risk_reward": {
                "ratio": round(rr_ratio, 2),
                "is_favorable": rr_ratio >= 2
            },

            "trend": {
                "direction": trend,
                "price_vs_sma20": "ABOVE" if current_price > sma_20 else "BELOW",
                "price_vs_sma50": "ABOVE" if current_price > sma_50 else "BELOW",
                "price_vs_sma200": "ABOVE" if current_price > sma_200 else "BELOW"
            },

            "recommendation": {
                "action": recommendation,
                "reasoning": reasoning,
                "entry_zone": f"{round(stop_loss, 2)} - {round(current_price * 1.01, 2)}",
                "position_size_tip": "Risk max 2% of capital per trade"
            },

            "swing_trade_setup": {
                "entry": round(current_price, 2),
                "stop_loss": round(stop_loss, 2),
                "target_1": round(target_1, 2),
                "target_2": round(target_2, 2),
                "potential_gain_pct": round(target_1_gain, 2),
                "max_risk_pct": round(stop_loss_risk, 2),
                "holding_period": "3-10 trading days"
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating levels for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CHIEF ANALYST REPORT ENDPOINTS ====================

@app.get("/api/analyst/report/{symbol}")
async def get_chief_analyst_report(symbol: str):
    """
    Generate a full BSE Chief Equity Analyst report for a single stock.
    Synthesizes technicals + fundamentals + news + sector rotation
    into a structured, decision-oriented research note.
    """
    try:
        # Load technical data from DB
        with db.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                WHERE e.symbol = ?
                ORDER BY e.trade_date
                """,
                conn,
                params=[symbol.upper()]
            )

        sector = SECTOR_MAP.get(symbol.upper(), "Unknown")
        report = generate_chief_analyst_report(
            symbol=symbol.upper(),
            technical_df=df if not df.empty else None,
            sector=sector,
        )

        return convert_to_native(report)

    except Exception as e:
        logger.error(f"Error generating analyst report for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyst/sector-rotation/{sector}")
async def get_sector_rotation(sector: str):
    """
    Get sector rotation status — sector index vs NIFTY 50
    relative strength over 1M, 3M, 6M with regime classification.
    """
    try:
        result = calculate_sector_rotation_status(sector)
        return convert_to_native(result)
    except Exception as e:
        logger.error(f"Error in sector rotation for {sector}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WEEKLY SWING PICKS - THE ULTIMATE STRATEGY ====================

@app.get("/api/weekly-swing-picks")
async def get_weekly_swing_picks():
    """
    Weekly Swing Picks - Using the Elite Momentum Strategy (68% Win Rate)
    enhanced with full Chief Analyst reports.

    Returns exactly 2 top stocks with comprehensive research-grade analysis:
    scorecard, scenarios, catalysts, risks, and trading/investing plan.
    """
    try:
        current_date = datetime.now()
        week_number = current_date.isocalendar()[1]

        cache_key = f"weekly_picks_v3_w{week_number}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"Returning cached weekly picks for week {week_number}")
            return JSONResponse(cached)

        with db.get_connection() as conn:
            latest_date = pd.read_sql_query(
                "SELECT MAX(trade_date) as max_date FROM eod", conn
            ).iloc[0]["max_date"]

            try:
                data_date = datetime.strptime(latest_date, "%Y-%m-%d")
                data_age_days = (current_date - data_date).days
            except Exception:
                data_age_days = 0

            fresh_symbols = pd.read_sql_query(
                "SELECT DISTINCT symbol FROM eod WHERE trade_date = ?",
                conn,
                params=[latest_date],
            )["symbol"].tolist()

            df = pd.read_sql_query(
                """
                SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
                       e.volume, e.turnover, e.prev_close,
                       i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
                FROM eod e
                LEFT JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
                ORDER BY e.symbol, e.trade_date
                """,
                conn,
            )

        if df.empty:
            return JSONResponse({"picks": [], "message": "No data available"})

        df = df[df["symbol"].isin(fresh_symbols)]
        if df.empty:
            return JSONResponse({"picks": [], "message": "No stocks with current data"})

        df["sector"] = df["symbol"].map(SECTOR_MAP).fillna("Unknown")
        logger.info(f"Running weekly picks screener with {len(fresh_symbols)} fresh stocks...")

        # Run elite screener for initial candidate list
        elite_result = run_elite_screener(
            df=df, top_n=10, capital_per_trade=100000,
            min_score=60, min_price=100, sector_filter=True,
        )

        if not elite_result or not elite_result.get("candidates"):
            return JSONResponse({
                "picks": [],
                "message": elite_result.get("message", "No qualifying stocks this week"),
                "market_regime": elite_result.get("market_regime"),
            })

        all_candidates = elite_result.get("candidates", [])

        # Week-based rotation for stale data
        if data_age_days > 7 and len(all_candidates) > 2:
            rotation_offset = (week_number % max(1, len(all_candidates) // 2)) * 2
            selected = all_candidates[rotation_offset : rotation_offset + 2]
            if len(selected) < 2:
                selected = all_candidates[:2]
        else:
            selected = all_candidates[:2]

        # Generate full Chief Analyst report for each pick
        picks = []
        for candidate in selected:
            symbol = candidate["symbol"]
            sector = candidate.get("sector", "Unknown")
            entry_price = candidate["entry_price"]
            stop_loss = candidate["stop_loss"]
            risk_pct = abs((entry_price - stop_loss) / entry_price * 100)
            score_breakdown = candidate.get("score_breakdown", {})
            metrics = candidate.get("metrics", {})

            # Generate full analyst report
            try:
                analyst_report = generate_chief_analyst_report(
                    symbol=symbol, technical_df=df, sector=sector,
                )
            except Exception as report_err:
                logger.warning(f"Analyst report failed for {symbol}: {report_err}")
                analyst_report = None

            pick = {
                "symbol": symbol,
                "sector": sector,
                "swing_score": candidate["score"],
                "current_price": entry_price,
                "factors": [
                    f"Elite Score: {candidate['score']}/100",
                    f"Breakout: {score_breakdown.get('breakout', 0)} pts",
                    f"Volume: {score_breakdown.get('volume', 0)} pts",
                    f"Momentum: {score_breakdown.get('momentum', 0)} pts",
                    f"Trend: {score_breakdown.get('trend', 0)} pts",
                ],
                "technical": {
                    "rsi": metrics.get("rsi_14", 50),
                    "vol_ratio": metrics.get("vol_ratio", 1.0),
                    "range_position": metrics.get("range_position", 0.5),
                    "atr_pct": round(metrics.get("atr_14", 0) / entry_price * 100, 2) if metrics.get("atr_14") else None,
                    "dist_from_52w_high": None,
                },
                "trade_setup": {
                    "entry_price": entry_price,
                    "entry_zone": f"{round(entry_price * 0.99, 2)} - {round(entry_price * 1.01, 2)}",
                    "stop_loss": stop_loss,
                    "stop_loss_pct": round(risk_pct, 2),
                    "target_1": candidate.get("target_price", entry_price * 1.02),
                    "target_1_pct": round(((candidate.get("target_price", entry_price * 1.02) - entry_price) / entry_price) * 100, 2),
                    "target_2": round(entry_price * 1.04, 2),
                    "target_2_pct": 4.0,
                    "target_3": round(entry_price * 1.06, 2),
                    "target_3_pct": 6.0,
                    "risk_reward_ratio": candidate.get("risk_reward", 2.0),
                    "position_size_tip": f"Risk 2% of capital = Stop at {round(risk_pct, 1)}% loss",
                    "holding_period": "3-7 trading days",
                    "exit_strategy": "Book 50% at Target 1, trail stop for rest",
                },
                "confidence": (
                    "HIGH" if candidate["score"] >= 85
                    else "MEDIUM" if candidate["score"] >= 70
                    else "MODERATE"
                ),
                # Chief Analyst Report fields
                "analyst_report": analyst_report,
            }
            picks.append(pick)

        week_start = current_date - timedelta(days=current_date.weekday())
        week_end = week_start + timedelta(days=4)

        if data_age_days <= 1:
            freshness_status, freshness_message = "FRESH", "Data is current and up-to-date"
        elif data_age_days <= 7:
            freshness_status = "RECENT"
            freshness_message = f"Data is {data_age_days} days old"
        else:
            freshness_status = "STALE"
            freshness_message = f"Data is {data_age_days} days old - fetch new data for accurate picks"

        alternatives = []
        for alt in all_candidates[:6]:
            if alt["symbol"] not in [p["symbol"] for p in picks]:
                alternatives.append({
                    "symbol": alt["symbol"],
                    "sector": alt.get("sector", "Unknown"),
                    "score": alt["score"],
                    "price": alt["entry_price"],
                })

        result = {
            "picks": picks,
            "total_candidates_analyzed": elite_result.get("stats", {}).get("total_stocks", 0),
            "qualified_candidates": len(all_candidates),
            "data_freshness": {
                "status": freshness_status,
                "message": freshness_message,
                "data_date": latest_date,
                "age_days": data_age_days,
                "week_rotation": week_number if data_age_days > 7 else None,
            },
            "alternatives": alternatives[:4],
            "strategy": {
                "week": f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}",
                "strategy_name": "Elite Momentum + Chief Analyst (68% Win Rate)",
                "expected_return": "2-5% per trade",
                "win_rate_historical": "68%",
                "max_positions": 2,
                "capital_per_trade": "50% each (diversified)",
                "key_rules": [
                    "Enter only within the entry zone",
                    "Always use stop loss - no exceptions",
                    "Book 50% profit at Target 1",
                    "Trail stop loss after Target 1 hit",
                    "Exit all positions by Friday if targets not hit",
                    "Never average down on losing positions",
                ],
            },
            "market_regime": elite_result.get("market_regime"),
            "generated_at": current_date.strftime("%Y-%m-%d %H:%M"),
            "data_date": latest_date,
            "disclaimer": "This is algorithmic analysis, not financial advice. Always do your own research.",
        }

        cache.set(cache_key, convert_to_native(result), ttl=3600)
        logger.info(f"Cached weekly picks for week {week_number}")

        return JSONResponse(convert_to_native(result))

    except Exception as e:
        logger.error(f"Error generating weekly picks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
