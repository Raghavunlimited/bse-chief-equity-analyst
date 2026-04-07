# NSE Weekly Swing Trader - Copilot Instructions

## Architecture Overview

Full-stack NSE stock screener: **FastAPI backend** (Python 3.11+) + **React 18 frontend**.

```
Data Flow: NSE Bhavcopy → ingest.py → SQLite (eod/indicators/screener_results tables) 
         → features.py (indicators) → screener modules → REST API → React UI
```

### Backend Structure (`backend/app/`)
- `main.py` - FastAPI app with all endpoints (monolithic)
- `config.py` - Trading params (2% risk, ATR multiples, RSI thresholds)
- `store.py` - SQLite via `Database` class; always use `db.get_connection()` context manager
- `ingest.py` - `NSEDataIngester` downloads from NSE archives
- `features.py` - Technical indicators (RSI, ATR, SMA); use `compute_indicators_for_all_symbols()`
- `screener.py` - Basic screener (8-point scoring: trend/momentum/breakout/volume)
- `ultimate_screener.py` - Production screener combining patterns, sector, trend (0-100 score)
- `elite_screener.py` - Elite Momentum Screener v2.0 with institutional-grade filters
- `chief_analyst.py` - BSE Chief Equity Analyst Report Generator (synthesizes all modules)
- `financial_analysis.py` - Yahoo Finance fundamentals + earnings quality + governance scoring
- `news_analyzer.py` - Multi-source news (RSS, NSE API, yfinance, Google News) with SEBI LODR analysis
- `multibagger_screener.py` - Long-term fundamental screening (2-10x potential)
- `sector_analysis.py` - Sector rotation, heatmaps, relative strength
- `nse_stocks.py` - `SECTOR_MAP` dict mapping 1000+ symbols to sectors

### Frontend Structure (`frontend/src/`)
- `App.js` - Main component with screener modes: 'basic', 'enhanced', 'ultimate'
- `services/api.js` - `screenerAPI` object wraps all backend calls
- Components: `CandidateCard`, `SectorHeatmap`, `BacktestPanel`, etc.

## Developer Workflow

```bash
# Quick start (handles venv + npm install if missing)
./start.sh

# Manual startup
cd backend && source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000

cd frontend && npm start  # Port 3000
```

API docs at `http://localhost:8000/docs` (Swagger UI).

## Critical Patterns

### JSON Serialization
Always use `convert_to_native()` from `sector_analysis.py` before returning numpy/pandas data:
```python
from app.sector_analysis import convert_to_native
return convert_to_native(result_dict)  # Handles np.int64, np.float64, np.bool_, etc.
```

### Database Access
```python
from app.config import config
from app.store import Database
db = Database(config.db_path)
with db.get_connection() as conn:
    df = pd.read_sql_query("SELECT * FROM eod WHERE symbol=?", conn, params=[symbol])
```

### Adding New Indicators
1. Add calculation to `features.py` in `add_indicators()` function
2. Update `DB_SCHEMA` in `store.py` if persisting to indicators table
3. Use in screener via the dataframe column

### Sector Mapping
```python
from nse_stocks import SECTOR_MAP
sector = SECTOR_MAP.get(symbol, "Unknown")
```

## API Endpoint Convention

All endpoints in `main.py` follow pattern:
- GET `/api/screener/*` - Read screener results
- POST `/api/screener/run`, `/api/screener/enhanced`, `/api/screener/ultimate` - Run screeners
- GET `/api/sector-*` - Sector analysis endpoints
- POST `/api/ingest/latest` - Fetch new NSE data
- GET `/api/analyst/report/{symbol}` - Chief Analyst full research report
- GET `/api/analyst/sector-rotation/{sector}` - Sector vs NIFTY 50 relative strength
- GET `/api/weekly-swing-picks` - Weekly 2-stock picks with analyst reports
- GET `/api/news/latest` - Multi-source news with SEBI analysis
- GET `/api/news/symbol/{symbol}` - News for a specific stock

## Scoring System

**Basic Screener** (8-point max): trend(2) + momentum(2) + breakout(2) + volume(1) + above_sma20(1)

**Ultimate Screener** (100-point): pattern(25) + trend(25) + sector(20) + volume(15) + entry_quality(15)

**Elite Screener** (100-point): breakout(35) + volume(25) + momentum(25) + trend(15)

**Chief Analyst Scorecard** (0-10 each): Long-Term + Short-Term + Risk + Valuation + Quality

**Financial Score** (0-100): profitability(25) + debt(20) + growth(20) + valuation(15) + promoter(10) + dividend(10)

**Earnings Quality** (0-30): cash_conversion(10) + accrual_ratio(10) + revenue_consistency(10) → Grade A/B/C/D

**Governance Score** (0-25): promoter_holding(8) + institutional(5) + stability(3) + payout(4) + solvency(5) → Grade A/B/C/D

## Key Trading Parameters (from `config.py`)
- `risk_per_trade`: 0.02 (2%)
- `min_traded_value`: 10 Cr INR
- `stop_loss_atr_multiple`: 1.0
- `target_atr_multiple`: 2.0
- `rsi_min/max`: 55-70 (constructive zone)

## Testing Changes

No formal test suite. Validate by:
1. Start backend, check `/docs` works
2. Run `python run_weekly_screen.py` from backend/
3. Frontend: verify screener results render

## Common Gotchas

- **Imports**: Use `from app.module import X` (not relative imports)
- **Date handling**: NSE uses `%d%b%Y` format (e.g., `03FEB2026`)
- **Empty dataframes**: Always check `if df.empty` before processing
- **NaN handling**: Use `df.dropna(subset=[...])` for critical fields before calculations
