import React, { useState, useEffect, useRef } from 'react';
import { screenerAPI } from '../services/api';
import { 
  Search, X, TrendingUp, TrendingDown, Target, AlertTriangle, 
  DollarSign, Activity, BarChart2, ArrowUpRight, ArrowDownRight,
  Shield, Crosshair, Minus, Calendar, AlertCircle, FileText, 
  PieChart, CheckCircle, XCircle, Award, Briefcase, Building2
} from 'lucide-react';

// Helper to check if data is stale (more than 7 days old)
const isDataStale = (lastUpdated) => {
  if (!lastUpdated) return true;
  const dataDate = new Date(lastUpdated);
  const today = new Date();
  const diffDays = Math.floor((today - dataDate) / (1000 * 60 * 60 * 24));
  return diffDays > 7;
};

// Format date nicely
const formatDate = (dateStr) => {
  if (!dateStr) return 'Unknown';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-IN', { 
    day: 'numeric', 
    month: 'short', 
    year: 'numeric' 
  });
};

// Format currency value
const formatCurrency = (value) => {
  if (!value) return '-';
  if (typeof value === 'object') {
    return `${value.value >= 0 ? '' : '-'}₹${Math.abs(value.value).toLocaleString()} ${value.unit}`;
  }
  return `₹${value.toLocaleString()}`;
};

// Format percentage
const formatPct = (value) => {
  if (value === null || value === undefined) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
};

// Score color helper
const getScoreColor = (score) => {
  if (score >= 70) return '#10b981';
  if (score >= 50) return '#fbbf24';
  if (score >= 30) return '#f97316';
  return '#ef4444';
};

const StockSearchModal = ({ isOpen, onClose }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockData, setStockData] = useState(null);
  const [financialData, setFinancialData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [financialLoading, setFinancialLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('technical');
  const [capital, setCapital] = useState(100000);
  const searchInputRef = useRef(null);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
    if (!isOpen) {
      setSearchQuery('');
      setSearchResults([]);
      setSelectedStock(null);
      setStockData(null);
      setFinancialData(null);
      setActiveTab('technical');
    }
  }, [isOpen]);

  // Search stocks as user types
  useEffect(() => {
    const searchStocks = async () => {
      if (searchQuery.length < 1) {
        setSearchResults([]);
        return;
      }
      
      setSearchLoading(true);
      try {
        const data = await screenerAPI.searchStocks(searchQuery);
        setSearchResults(data.results || []);
      } catch (err) {
        console.error('Search error:', err);
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    };

    const debounce = setTimeout(searchStocks, 300);
    return () => clearTimeout(debounce);
  }, [searchQuery]);

  // Fetch comprehensive analysis when stock is selected
  const handleSelectStock = async (symbol) => {
    setSelectedStock(symbol);
    setLoading(true);
    setFinancialLoading(true);
    setSearchResults([]);
    setSearchQuery(symbol);
    setActiveTab('technical');
    
    // Fetch technical analysis
    try {
      const data = await screenerAPI.getComprehensiveAnalysis(symbol, capital);
      setStockData(data);
    } catch (err) {
      console.error('Failed to get stock data:', err);
      setStockData(null);
    } finally {
      setLoading(false);
    }

    // Fetch financial analysis
    try {
      const finData = await screenerAPI.getFinancialAnalysis(symbol);
      setFinancialData(finData);
    } catch (err) {
      console.error('Failed to get financial data:', err);
      setFinancialData({ error: 'Could not fetch financial data' });
    } finally {
      setFinancialLoading(false);
    }
  };

  // Handle direct search (Enter key)
  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.length >= 1) {
      handleSelectStock(searchQuery.toUpperCase());
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="stock-search-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h3><Search size={20} /> Stock Analysis</h3>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="search-form">
          <div className="search-input-wrapper">
            <Search size={18} className="search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Enter stock symbol (e.g., RELIANCE, TCS, INFY)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
              className="search-input"
            />
            {searchQuery && (
              <button 
                type="button" 
                className="clear-btn"
                onClick={() => {
                  setSearchQuery('');
                  setSelectedStock(null);
                  setStockData(null);
                  setFinancialData(null);
                }}
              >
                <X size={16} />
              </button>
            )}
          </div>
          
          {/* Search Results Dropdown */}
          {searchResults.length > 0 && !selectedStock && (
            <div className="search-dropdown">
              {searchResults.map((result) => (
                <div 
                  key={result.symbol}
                  className="search-result-item"
                  onClick={() => handleSelectStock(result.symbol)}
                >
                  <span className="result-symbol">{result.symbol}</span>
                  <span className="result-sector">{result.sector}</span>
                </div>
              ))}
            </div>
          )}
        </form>

        {/* Tab Navigation */}
        {selectedStock && (stockData || loading) && (
          <div className="analysis-tabs">
            <button 
              className={`tab-btn ${activeTab === 'technical' ? 'active' : ''}`}
              onClick={() => setActiveTab('technical')}
            >
              <Target size={16} />
              <span>Technical Analysis</span>
            </button>
            <button 
              className={`tab-btn ${activeTab === 'financials' ? 'active' : ''}`}
              onClick={() => setActiveTab('financials')}
            >
              <FileText size={16} />
              <span>Financials</span>
              {financialData?.financial_score && (
                <span 
                  className="tab-score"
                  style={{ backgroundColor: getScoreColor(financialData.financial_score.percentage) }}
                >
                  {financialData.financial_score.percentage}
                </span>
              )}
            </button>
          </div>
        )}

        {/* Loading State */}
        {loading && activeTab === 'technical' && (
          <div className="loading-state">
            <Activity size={24} className="spinning" />
            <span>Analyzing {selectedStock}...</span>
          </div>
        )}

        {financialLoading && activeTab === 'financials' && (
          <div className="loading-state">
            <Activity size={24} className="spinning" />
            <span>Fetching financial data...</span>
          </div>
        )}

        {/* Technical Analysis Tab */}
        {activeTab === 'technical' && stockData && !loading && (
          <div className="analysis-content">
            {/* Stale Data Warning */}
            {isDataStale(stockData.last_updated) && (
              <div className="stale-data-warning">
                <AlertCircle size={18} />
                <div>
                  <strong>Stale Data Warning</strong>
                  <p>Data is from {formatDate(stockData.last_updated)}. Prices may have changed significantly. Use "Update Data" button to refresh.</p>
                </div>
              </div>
            )}

            {/* Stock Header */}
            <div className="stock-header">
              <div className="stock-info">
                <h2>{stockData.symbol}</h2>
                <span className="sector-badge">{stockData.sector}</span>
                <span className="data-date">
                  <Calendar size={12} />
                  {formatDate(stockData.last_updated)}
                </span>
              </div>
              <div className="price-info">
                <span className="current-price">₹{stockData.price_data.current_price.toLocaleString()}</span>
                <span className={`price-change ${stockData.price_data.daily_change_pct >= 0 ? 'positive' : 'negative'}`}>
                  {stockData.price_data.daily_change_pct >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                  {stockData.price_data.daily_change_pct.toFixed(2)}%
                </span>
              </div>
            </div>

            {/* Recommendation Banner */}
            <div className={`recommendation-banner ${stockData.recommendation.action_color}`}>
              <div className="rec-action">
                {stockData.recommendation.action === 'STRONG BUY' || stockData.recommendation.action === 'BUY' ? 
                  <TrendingUp size={24} /> : 
                  stockData.recommendation.action === 'AVOID' ? 
                  <TrendingDown size={24} /> : 
                  <Minus size={24} />}
                <span>{stockData.recommendation.action}</span>
              </div>
              <div className="rec-score">
                Score: {stockData.recommendation.score}/100
              </div>
            </div>

            {/* Investment Zones - Main Feature */}
            <div className="investment-zones-card">
              <h4><Target size={18} /> Investment Zones</h4>
              
              <div className="zones-grid">
                <div className="zone-card entry">
                  <div className="zone-label">Entry Zone</div>
                  <div className="zone-value">
                    ₹{stockData.investment_zones.entry_zone.low.toLocaleString()} - ₹{stockData.investment_zones.entry_zone.high.toLocaleString()}
                  </div>
                  <div className="zone-note">{stockData.investment_zones.entry_zone.note}</div>
                </div>
                
                <div className="zone-card stoploss">
                  <div className="zone-label">Stop Loss</div>
                  <div className="zone-value">₹{stockData.investment_zones.stop_loss.price.toLocaleString()}</div>
                  <div className="zone-note">-{stockData.investment_zones.stop_loss.pct_from_entry}% from entry</div>
                </div>
                
                {stockData.investment_zones.targets.map((target, idx) => (
                  <div key={idx} className={`zone-card target target-${idx + 1}`}>
                    <div className="zone-label">{target.name}</div>
                    <div className="zone-value">₹{target.price.toLocaleString()}</div>
                    <div className="zone-note">+{target.pct_gain}%</div>
                  </div>
                ))}
              </div>

              <div className="risk-reward-bar">
                <Shield size={16} />
                Risk:Reward = 1:{stockData.investment_zones.risk_reward_ratio}
              </div>
            </div>

            {/* Technical Indicators */}
            <div className="technicals-grid">
              <div className="tech-card">
                <div className="tech-label">RSI (14)</div>
                <div className={`tech-value ${
                  stockData.technicals.rsi_14 >= 70 ? 'overbought' : 
                  stockData.technicals.rsi_14 <= 30 ? 'oversold' : 
                  stockData.technicals.rsi_14 >= 55 ? 'bullish' : 'neutral'
                }`}>
                  {stockData.technicals.rsi_14}
                </div>
                <div className="tech-signal">{stockData.technicals.rsi_signal}</div>
              </div>
              
              <div className="tech-card">
                <div className="tech-label">Trend</div>
                <div className={`tech-value ${stockData.trend.direction.toLowerCase()}`}>
                  {stockData.trend.direction === 'BULLISH' ? <TrendingUp size={20} /> : 
                   stockData.trend.direction === 'BEARISH' ? <TrendingDown size={20} /> : 
                   <Minus size={20} />}
                </div>
                <div className="tech-signal">{stockData.trend.direction}</div>
              </div>
              
              <div className="tech-card">
                <div className="tech-label">Volume</div>
                <div className={`tech-value ${stockData.technicals.vol_ratio >= 1.5 ? 'high' : 'normal'}`}>
                  {stockData.technicals.vol_ratio.toFixed(1)}x
                </div>
                <div className="tech-signal">{stockData.technicals.volume_signal}</div>
              </div>
              
              <div className="tech-card">
                <div className="tech-label">From 20D High</div>
                <div className={`tech-value ${stockData.price_data.dist_from_20d_high_pct <= 3 ? 'near-high' : 'normal'}`}>
                  -{stockData.price_data.dist_from_20d_high_pct}%
                </div>
                <div className="tech-signal">{stockData.price_data.dist_from_20d_high_pct <= 3 ? 'Near High' : 'Below High'}</div>
              </div>
            </div>

            {/* Position Sizing */}
            <div className="position-sizing-card">
              <h4><DollarSign size={18} /> Position Sizing (Capital: ₹{capital.toLocaleString()})</h4>
              <div className="position-grid">
                <div className="pos-item">
                  <span className="pos-label">Shares to Buy</span>
                  <span className="pos-value">{stockData.position_sizing.shares}</span>
                </div>
                <div className="pos-item">
                  <span className="pos-label">Position Value</span>
                  <span className="pos-value">₹{stockData.position_sizing.position_value.toLocaleString()}</span>
                </div>
                <div className="pos-item">
                  <span className="pos-label">Max Risk</span>
                  <span className="pos-value">₹{stockData.position_sizing.max_risk_amount.toLocaleString()} (2%)</span>
                </div>
                <div className="pos-item">
                  <span className="pos-label">% of Capital</span>
                  <span className="pos-value">{stockData.position_sizing.pct_of_capital}%</span>
                </div>
              </div>
            </div>

            {/* Key Levels */}
            <div className="levels-grid">
              <div className="levels-card">
                <h4><Crosshair size={16} /> Support Levels</h4>
                {stockData.support_resistance.supports.map((s, idx) => (
                  <div key={idx} className="level-item support">
                    <span>{s.name}</span>
                    <span>₹{s.level.toLocaleString()}</span>
                  </div>
                ))}
              </div>
              <div className="levels-card">
                <h4><Target size={16} /> Resistance Levels</h4>
                {stockData.support_resistance.resistances.map((r, idx) => (
                  <div key={idx} className="level-item resistance">
                    <span>{r.name}</span>
                    <span>₹{r.level.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Analysis Reasons */}
            <div className="reasons-card">
              <h4><BarChart2 size={18} /> Analysis Breakdown</h4>
              <ul className="reasons-list">
                {stockData.recommendation.reasons.map((reason, idx) => (
                  <li key={idx}>{reason}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Financial Analysis Tab */}
        {activeTab === 'financials' && !financialLoading && (
          <div className="analysis-content financials-tab">
            {financialData?.error ? (
              <div className="financial-error">
                <AlertCircle size={24} />
                <p>{financialData.error}</p>
                <p className="hint">Financial data may not be available for all stocks.</p>
              </div>
            ) : financialData && (
              <>
                {/* Company Header */}
                <div className="company-header">
                  <div className="company-info">
                    <Building2 size={24} />
                    <div>
                      <h2>{financialData.company_name}</h2>
                      <span>{financialData.sector} • {financialData.industry}</span>
                    </div>
                  </div>
                  <div className="market-cap">
                    <span className="label">Market Cap</span>
                    <span className="value">
                      {financialData.market_cap ? `₹${(financialData.market_cap / 1e9).toFixed(2)}B` : '-'}
                    </span>
                  </div>
                </div>

                {/* Financial Strength Score */}
                {financialData.financial_score && (
                  <div className="financial-score-card">
                    <div className="score-header">
                      <Award size={20} />
                      <h4>Financial Strength Score</h4>
                    </div>
                    <div className="score-main">
                      <div 
                        className="score-circle"
                        style={{ 
                          '--score-color': getScoreColor(financialData.financial_score.percentage),
                          '--score-pct': `${financialData.financial_score.percentage}%`
                        }}
                      >
                        <span className="score-number">{financialData.financial_score.total_score}</span>
                        <span className="score-max">/{financialData.financial_score.max_score}</span>
                      </div>
                      <div className="score-rating">
                        <span className="rating" style={{ color: getScoreColor(financialData.financial_score.percentage) }}>
                          {financialData.financial_score.rating}
                        </span>
                        <span className="risk">Risk: {financialData.analysis?.risk_level}</span>
                      </div>
                    </div>
                    
                    {/* Score Breakdown */}
                    <div className="score-breakdown">
                      {Object.entries(financialData.financial_score.breakdown).map(([key, data]) => (
                        <div key={key} className="breakdown-item">
                          <div className="breakdown-header">
                            <span className="breakdown-name">{key.replace('_', ' ')}</span>
                            <span className="breakdown-score">{data.score}/{data.max}</span>
                          </div>
                          <div className="breakdown-bar">
                            <div 
                              className="breakdown-fill"
                              style={{ width: `${(data.score / data.max) * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Key Ratios */}
                <div className="ratios-section">
                  <h4><PieChart size={18} /> Key Financial Ratios</h4>
                  <div className="ratios-grid">
                    <div className="ratio-group">
                      <h5>Valuation</h5>
                      <div className="ratio-item">
                        <span>P/E Ratio</span>
                        <span className={financialData.pe_ratio < 20 ? 'good' : financialData.pe_ratio > 40 ? 'bad' : ''}>
                          {financialData.pe_ratio || '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>P/B Ratio</span>
                        <span>{financialData.pb_ratio || '-'}</span>
                      </div>
                      <div className="ratio-item">
                        <span>PEG Ratio</span>
                        <span className={financialData.peg_ratio < 1 ? 'good' : financialData.peg_ratio > 2 ? 'bad' : ''}>
                          {financialData.peg_ratio || '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>EV/EBITDA</span>
                        <span>{financialData.ev_ebitda || '-'}</span>
                      </div>
                    </div>
                    
                    <div className="ratio-group">
                      <h5>Profitability</h5>
                      <div className="ratio-item">
                        <span>ROE</span>
                        <span className={financialData.roe > 15 ? 'good' : financialData.roe < 10 ? 'bad' : ''}>
                          {financialData.roe ? `${financialData.roe}%` : '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>ROA</span>
                        <span>{financialData.roa ? `${financialData.roa}%` : '-'}</span>
                      </div>
                      <div className="ratio-item">
                        <span>Profit Margin</span>
                        <span className={financialData.profit_margin > 15 ? 'good' : financialData.profit_margin < 5 ? 'bad' : ''}>
                          {financialData.profit_margin ? `${financialData.profit_margin}%` : '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>Operating Margin</span>
                        <span>{financialData.operating_margin ? `${financialData.operating_margin}%` : '-'}</span>
                      </div>
                    </div>
                    
                    <div className="ratio-group">
                      <h5>Debt & Liquidity</h5>
                      <div className="ratio-item">
                        <span>Debt/Equity</span>
                        <span className={financialData.debt_to_equity < 0.5 ? 'good' : financialData.debt_to_equity > 1.5 ? 'bad' : ''}>
                          {financialData.debt_to_equity || '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>Current Ratio</span>
                        <span className={financialData.current_ratio > 1.5 ? 'good' : financialData.current_ratio < 1 ? 'bad' : ''}>
                          {financialData.current_ratio || '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>Quick Ratio</span>
                        <span>{financialData.quick_ratio || '-'}</span>
                      </div>
                    </div>
                    
                    <div className="ratio-group">
                      <h5>Growth & Returns</h5>
                      <div className="ratio-item">
                        <span>Revenue Growth</span>
                        <span className={financialData.revenue_growth > 10 ? 'good' : financialData.revenue_growth < 0 ? 'bad' : ''}>
                          {financialData.revenue_growth ? `${financialData.revenue_growth}%` : '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>5Y Return</span>
                        <span className={financialData.five_year_return > 50 ? 'good' : financialData.five_year_return < 0 ? 'bad' : ''}>
                          {financialData.five_year_return ? `${financialData.five_year_return}%` : '-'}
                        </span>
                      </div>
                      <div className="ratio-item">
                        <span>Dividend Yield</span>
                        <span>{financialData.dividend_yield ? `${financialData.dividend_yield}%` : '-'}</span>
                      </div>
                      <div className="ratio-item">
                        <span>EPS</span>
                        <span>₹{financialData.eps || '-'}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Income Statement Summary */}
                {financialData.income_statement?.available && (
                  <div className="income-section">
                    <h4><BarChart2 size={18} /> Income Statement (5-Year Trend)</h4>
                    <div className="income-table">
                      <div className="income-header">
                        <span>Metric</span>
                        {financialData.income_statement.yearly_data?.map(y => (
                          <span key={y.year}>{y.year}</span>
                        ))}
                      </div>
                      <div className="income-row">
                        <span>Revenue</span>
                        {financialData.income_statement.yearly_data?.map(y => (
                          <span key={y.year}>{formatCurrency(y.revenue)}</span>
                        ))}
                      </div>
                      <div className="income-row">
                        <span>Net Income</span>
                        {financialData.income_statement.yearly_data?.map(y => (
                          <span key={y.year}>{formatCurrency(y.net_income)}</span>
                        ))}
                      </div>
                      <div className="income-row">
                        <span>EBITDA</span>
                        {financialData.income_statement.yearly_data?.map(y => (
                          <span key={y.year}>{formatCurrency(y.ebitda)}</span>
                        ))}
                      </div>
                    </div>
                    <div className="growth-badges">
                      <span className={`badge ${financialData.income_statement.revenue_growth_yoy >= 0 ? 'positive' : 'negative'}`}>
                        Revenue YoY: {formatPct(financialData.income_statement.revenue_growth_yoy)}
                      </span>
                      <span className={`badge ${financialData.income_statement.profit_growth_yoy >= 0 ? 'positive' : 'negative'}`}>
                        Profit YoY: {formatPct(financialData.income_statement.profit_growth_yoy)}
                      </span>
                    </div>
                  </div>
                )}

                {/* Balance Sheet Summary */}
                {financialData.balance_sheet?.available && (
                  <div className="balance-section">
                    <h4><Briefcase size={18} /> Balance Sheet Summary</h4>
                    <div className="balance-grid">
                      <div className="balance-item">
                        <span className="label">Total Assets</span>
                        <span className="value">{formatCurrency(financialData.balance_sheet.total_assets)}</span>
                      </div>
                      <div className="balance-item">
                        <span className="label">Total Liabilities</span>
                        <span className="value">{formatCurrency(financialData.balance_sheet.total_liabilities)}</span>
                      </div>
                      <div className="balance-item">
                        <span className="label">Total Equity</span>
                        <span className="value good">{formatCurrency(financialData.balance_sheet.total_equity)}</span>
                      </div>
                      <div className="balance-item">
                        <span className="label">Total Debt</span>
                        <span className="value">{formatCurrency(financialData.balance_sheet.total_debt)}</span>
                      </div>
                      <div className="balance-item">
                        <span className="label">Cash & Equivalents</span>
                        <span className="value good">{formatCurrency(financialData.balance_sheet.cash_and_equivalents)}</span>
                      </div>
                      <div className="balance-item">
                        <span className="label">Working Capital</span>
                        <span className="value">{formatCurrency(financialData.balance_sheet.working_capital)}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Cash Flow Summary */}
                {financialData.cash_flow?.available && (
                  <div className="cashflow-section">
                    <h4><DollarSign size={18} /> Cash Flow Summary</h4>
                    <div className="cashflow-grid">
                      <div className={`cashflow-item ${financialData.cash_flow.operating_cash_flow?.raw > 0 ? 'positive' : 'negative'}`}>
                        <span className="label">Operating Cash Flow</span>
                        <span className="value">{formatCurrency(financialData.cash_flow.operating_cash_flow)}</span>
                      </div>
                      <div className={`cashflow-item ${financialData.cash_flow.free_cash_flow?.raw > 0 ? 'positive' : 'negative'}`}>
                        <span className="label">Free Cash Flow</span>
                        <span className="value">{formatCurrency(financialData.cash_flow.free_cash_flow)}</span>
                      </div>
                      <div className="cashflow-item">
                        <span className="label">CapEx</span>
                        <span className="value">{formatCurrency(financialData.cash_flow.capital_expenditure)}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Pros and Cons */}
                {financialData.analysis && (
                  <div className="pros-cons-section">
                    <div className="pros-card">
                      <h4><CheckCircle size={18} /> Strengths</h4>
                      <ul>
                        {financialData.analysis.pros?.map((pro, idx) => (
                          <li key={idx}>{pro}</li>
                        ))}
                        {(!financialData.analysis.pros || financialData.analysis.pros.length === 0) && (
                          <li className="empty">No significant strengths identified</li>
                        )}
                      </ul>
                    </div>
                    <div className="cons-card">
                      <h4><XCircle size={18} /> Weaknesses</h4>
                      <ul>
                        {financialData.analysis.cons?.map((con, idx) => (
                          <li key={idx}>{con}</li>
                        ))}
                        {(!financialData.analysis.cons || financialData.analysis.cons.length === 0) && (
                          <li className="empty">No significant weaknesses identified</li>
                        )}
                      </ul>
                    </div>
                  </div>
                )}

                {/* Investment Thesis */}
                {financialData.analysis && (
                  <div className="thesis-section">
                    <h4><Target size={18} /> Investment Thesis</h4>
                    <p className="thesis-text">{financialData.analysis.investment_thesis}</p>
                    <div className="recommendation-badge" style={{ 
                      backgroundColor: financialData.analysis.risk_level === 'Low' ? 'rgba(16, 185, 129, 0.2)' :
                                       financialData.analysis.risk_level === 'Medium' ? 'rgba(251, 191, 36, 0.2)' :
                                       'rgba(239, 68, 68, 0.2)',
                      borderColor: financialData.analysis.risk_level === 'Low' ? 'rgba(16, 185, 129, 0.5)' :
                                   financialData.analysis.risk_level === 'Medium' ? 'rgba(251, 191, 36, 0.5)' :
                                   'rgba(239, 68, 68, 0.5)'
                    }}>
                      {financialData.analysis.recommendation}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Empty State */}
        {!loading && !stockData && !searchResults.length && searchQuery === '' && (
          <div className="empty-state">
            <Search size={48} />
            <p>Search for any NSE stock to get detailed analysis</p>
            <p className="hint">Try: RELIANCE, TCS, INFY, HDFCBANK</p>
          </div>
        )}

        {/* Disclaimer */}
        {(stockData || financialData) && (
          <div className="analysis-disclaimer">
            <AlertTriangle size={14} />
            <span>This is for educational purposes only. Not financial advice. Do your own research.</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default StockSearchModal;
