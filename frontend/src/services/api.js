import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const screenerAPI = {
  // Get latest screener results
  getLatestResults: async (limit = 20) => {
    const response = await api.get(`/api/screener/latest?limit=${limit}`);
    return response.data;
  },

  // Get screener results for a specific date
  getResultsByDate: async (date, limit = 20) => {
    const response = await api.get(`/api/screener/by-date?date=${date}&limit=${limit}`);
    return response.data;
  },

  // Get available screening dates
  getAvailableDates: async () => {
    const response = await api.get('/api/available-dates');
    return response.data;
  },

  // Run screener now
  runScreener: async (topN = 20, capitalPerTrade = 100000) => {
    const response = await api.post('/api/screener/run', null, {
      params: { top_n: topN, capital_per_trade: capitalPerTrade }
    });
    return response.data;
  },

  // Ingest latest data
  ingestLatest: async () => {
    const response = await api.post('/api/ingest/latest');
    return response.data;
  },

  // Ingest historical data
  ingestHistorical: async (startDate, endDate) => {
    const response = await api.post('/api/ingest/historical', null, {
      params: { start_date: startDate, end_date: endDate }
    });
    return response.data;
  },

  // Run backtest
  runBacktest: async (startDate, endDate, capital = 1000000, maxPositions = 10) => {
    const response = await api.post('/api/backtest/run', {
      start_date: startDate,
      end_date: endDate,
      capital,
      max_positions: maxPositions
    });
    return response.data;
  },

  // Get stats
  getStats: async () => {
    const response = await api.get('/api/stats/overview');
    return response.data;
  },

  // Get stock details with pros/cons
  getStockDetails: async (symbol) => {
    const response = await api.get(`/api/stock/${symbol}`);
    return response.data;
  },

  // Get chart data for a stock
  getChartData: async (symbol, period = '3M') => {
    const response = await api.get(`/api/chart/${symbol}?period=${period}`);
    return response.data;
  },

  // Get score explanation
  getScoreExplanation: async () => {
    const response = await api.get('/api/score-explanation');
    return response.data;
  },

  // Get sector analysis
  getSectors: async () => {
    const response = await api.get('/api/sectors');
    return response.data;
  },

  // Get comprehensive sector rotation analysis
  getSectorAnalysis: async () => {
    const response = await api.get('/api/sector-analysis');
    return response.data;
  },

  // Get stocks in a specific sector
  getSectorStocks: async (sectorName, top_n = 5) => {
    const response = await api.get(`/api/sector/${encodeURIComponent(sectorName)}/stocks?top_n=${top_n}`);
    return response.data;
  },

  // Enhanced screener with all filters
  runEnhancedScreener: async (params = {}) => {
    const response = await api.post('/api/screener/enhanced', null, {
      params: {
        top_n: params.top_n || 10,
        capital_per_trade: params.capital_per_trade || 100000,
        min_score: params.min_score || 12,
        apply_market_filter: params.apply_market_filter !== false,
        apply_sector_filter: params.apply_sector_filter !== false,
        apply_sr_filter: params.apply_sr_filter !== false,
        apply_mtf_filter: params.apply_mtf_filter !== false,
        apply_fundamental_filter: params.apply_fundamental_filter !== false,
        top_sectors: params.top_sectors || 3
      }
    });
    return response.data;
  },

  // Get market regime
  getMarketRegime: async () => {
    const response = await api.get('/api/market-regime');
    return response.data;
  },

  // Get sector rotation analysis
  getSectorRotation: async (topN = 3) => {
    const response = await api.get(`/api/sector-rotation?top_n=${topN}`);
    return response.data;
  },

  // Get filter summary
  getFilterSummary: async () => {
    const response = await api.get('/api/filters/summary');
    return response.data;
  },

  // Get entry analysis for a stock
  getEntryAnalysis: async (symbol) => {
    const response = await api.get(`/api/stock/${symbol}/entry-analysis`);
    return response.data;
  },

  // Get position size calculation
  getPositionSize: async (symbol, capital = 100000) => {
    const response = await api.get(`/api/position-size/${symbol}?capital=${capital}`);
    return response.data;
  },

  // Get sector heatmap data with date range
  getSectorHeatmap: async (startDate = null, endDate = null) => {
    let url = '/api/sector-heatmap';
    const params = [];
    if (startDate) params.push(`start_date=${startDate}`);
    if (endDate) params.push(`end_date=${endDate}`);
    if (params.length > 0) url += '?' + params.join('&');
    const response = await api.get(url);
    return response.data;
  },

  // Ultimate Screener - Pattern Recognition + Trend + Sector Rotation
  runUltimateScreener: async (params = {}) => {
    const response = await api.post('/api/screener/ultimate', null, {
      params: {
        top_n: params.top_n || 20,
        capital_per_trade: params.capital_per_trade || 100000,
        min_score: params.min_score || 50,
        require_pattern: params.require_pattern !== false,
        require_trend: params.require_trend !== false,
        sector_filter: params.sector_filter !== false,
        max_risk_pct: params.max_risk_pct || 5.0
      }
    });
    return response.data;
  },

  // Get ultimate screener methodology
  getUltimateMethodology: async () => {
    const response = await api.get('/api/screener/ultimate/methodology');
    return response.data;
  },

  // Elite Momentum Screener - Backtested 68% win rate, 25% annual returns
  runEliteScreener: async (params = {}) => {
    const response = await api.post('/api/screener/elite', null, {
      params: {
        top_n: params.top_n || 2,
        capital_per_trade: params.capital_per_trade || 100000,
        min_score: params.min_score || 70,
        min_price: params.min_price || 100
      }
    });
    return response.data;
  },

  // Get elite screener methodology and backtest results
  getEliteMethodology: async () => {
    const response = await api.get('/api/screener/elite/methodology');
    return response.data;
  },

  // Get pattern analysis for a stock
  getStockPatterns: async (symbol) => {
    const response = await api.get(`/api/stock/${symbol}/patterns`);
    return response.data;
  },

  // Get sector performance across time periods (1d, 2d, 5d, 7d, 1m)
  getSectorPerformance: async () => {
    const response = await api.get('/api/sector-performance');
    return response.data;
  },

  // Get detailed performance for a specific sector
  getSectorDetailedPerformance: async (sectorName) => {
    const response = await api.get(`/api/sector/${encodeURIComponent(sectorName)}/performance`);
    return response.data;
  },

  // Start bulk historical data download (10 years)
  startBulkDownload: async (years = 10) => {
    const response = await api.post('/api/ingest/bulk', null, {
      params: { years }
    });
    return response.data;
  },

  // Get bulk download status
  getBulkDownloadStatus: async () => {
    const response = await api.get('/api/ingest/bulk/status');
    return response.data;
  },

  // Search stocks by symbol
  searchStocks: async (query) => {
    const response = await api.get(`/api/stocks/search?q=${encodeURIComponent(query)}`);
    return response.data;
  },

  // Get comprehensive stock analysis with investment zones
  getComprehensiveAnalysis: async (symbol, capital = 100000) => {
    const response = await api.get(`/api/stock/${symbol}/comprehensive?capital=${capital}`);
    return response.data;
  },

  // Get financial analysis (balance sheet, income statement, ratios)
  getFinancialAnalysis: async (symbol) => {
    const response = await api.get(`/api/stock/${symbol}/financials`);
    return response.data;
  },

  // Get Chief Analyst report for a specific stock
  getAnalystReport: async (symbol) => {
    const response = await api.get(`/api/analyst/report/${symbol}`);
    return response.data;
  },

  // Get sector rotation status
  getSectorRotationStatus: async (sector) => {
    const response = await api.get(`/api/analyst/sector-rotation/${encodeURIComponent(sector)}`);
    return response.data;
  },

  // Get weekly swing picks (with analyst reports)
  getWeeklySwingPicks: async () => {
    const response = await api.get('/api/weekly-swing-picks');
    return response.data;
  },

  // Get latest news
  getLatestNews: async (forceRefresh = false, days = 3) => {
    const response = await api.get(`/api/news/latest?force_refresh=${forceRefresh}&days=${days}`);
    return response.data;
  },

  // Get news for a specific symbol
  getNewsForSymbol: async (symbol) => {
    const response = await api.get(`/api/news/symbol/${symbol}`);
    return response.data;
  },

  // Get actionable news signals
  getNewsSignals: async (minConfidence = 50) => {
    const response = await api.get(`/api/news/signals?min_confidence=${minConfidence}`);
    return response.data;
  },
};
