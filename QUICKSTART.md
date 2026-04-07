# Quick Start Guide

Get your NSE Swing Trader up and running in 5 minutes!

## Step 1: Install Dependencies

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend
```bash
cd frontend
npm install
```

## Step 2: Start the Application

### Terminal 1 - Backend API
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Wait for: `Application startup complete.`

### Terminal 2 - Frontend
```bash
cd frontend
npm start
```

Browser will automatically open at `http://localhost:3000`

## Step 3: Load Initial Data

**Option A: Using the Web Interface** (Recommended for first-time users)

1. Open the web app at `http://localhost:3000`
2. Click **"Fetch Latest Data"** button
3. Wait for data download and processing (2-3 minutes)
4. Click **"Run Screener"** to see candidates

**Option B: Using Command Line**

Download recent historical data (recommended - 60 days):
```bash
cd backend
source venv/bin/activate
python -c "
from datetime import datetime, timedelta
from app.ingest import NSEDataIngester
from app.config import config
from app.store import Database

# Calculate date range (last 60 days)
end = datetime.now()
start = end - timedelta(days=60)

# Download
ingester = NSEDataIngester(config.cache_dir, config.raw_dir)
paths = ingester.download_historical_range(start, end)
print(f'Downloaded {len(paths)} files')

# Store in database
db = Database(config.db_path)
for path in paths:
    df = ingester.load_bhavcopy_csv(path)
    db.upsert_eod_data(df)
"
```

Then compute indicators and run screener:
```bash
python run_daily_ingest.py  # Computes indicators
python run_weekly_screen.py  # Runs screener
```

## Step 4: Use the Application

### Web Interface

**Dashboard Features:**
- **Stats Overview**: See total stocks, data range, and latest candidates
- **Fetch Latest Data**: Download today's NSE data
- **Run Screener**: Find swing trade candidates
- **Backtest**: Test strategy on historical data

**Understanding Results:**

Each candidate shows:
- **Score**: 0-8 points (higher = stronger setup)
- **Entry Price**: Where to enter the trade
- **Stop Loss**: Where to exit if trade goes against you
- **Target Price**: Expected profit target
- **Risk:Reward**: How much you could gain vs lose
- **Position Size**: Number of shares based on 2% risk

### API Usage

**API Documentation:** `http://localhost:8000/docs`

**Example API Calls:**

Get latest results:
```bash
curl http://localhost:8000/api/screener/latest
```

Run screener:
```bash
curl -X POST http://localhost:8000/api/screener/run
```

Run backtest:
```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "capital": 1000000,
    "max_positions": 10
  }'
```

## Step 5: Daily Workflow

**Morning Routine** (after market close at ~3:45 PM IST):

```bash
cd backend
source venv/bin/activate
python run_daily_ingest.py   # Download latest data
```

**Weekly Routine** (Sunday evening):

```bash
python run_weekly_screen.py  # Get swing trade ideas
```

Or use the web interface:
1. Click "Fetch Latest Data"
2. Click "Run Screener"
3. Review candidates

## Troubleshooting

### Port Already in Use

**Backend (8000):**
```bash
# Find process
lsof -i :8000
# Kill it
kill -9 <PID>
```

**Frontend (3000):**
```bash
# Find process
lsof -i :3000
# Kill it
kill -9 <PID>
```

### No Data Available

1. Make sure backend is running
2. Click "Fetch Latest Data" in web interface
3. Wait for completion message
4. Then click "Run Screener"

### NSE Download Fails

- NSE data may not be available immediately after market close
- Try again after 6 PM IST
- Check internet connection
- NSE servers may be temporarily down

### React App Won't Start

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

## Next Steps

- **Customize Settings**: Edit `backend/app/config.py`
- **Backtest Strategy**: Use the Backtest panel in web interface
- **Set Up Cron Jobs**: Automate daily data fetch
- **Review API Docs**: Explore all endpoints at `/docs`

## Important Reminders

⚠️ **This is NOT financial advice**
- Always do your own research
- Never risk more than you can afford to lose
- Past performance doesn't guarantee future results

⚠️ **Respect NSE Terms**
- For personal use only
- Don't abuse rate limits
- Don't redistribute data

## Getting Help

Check the full README.md for:
- Detailed architecture explanation
- Configuration options
- Advanced usage
- Contributing guidelines

Happy trading! 📈
