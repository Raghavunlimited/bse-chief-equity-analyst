import React, { useState, useEffect } from 'react';
import { Calendar, TrendingUp, ChevronDown, ChevronUp, Target, Award, AlertCircle, X, Loader, ArrowRight } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const MONTH_COLORS = {
  'January': '#3b82f6',
  'February': '#ec4899',
  'March': '#10b981',
  'April': '#f59e0b',
  'May': '#8b5cf6',
  'June': '#06b6d4',
  'July': '#ef4444',
  'August': '#84cc16',
  'September': '#f97316',
  'October': '#6366f1',
  'November': '#14b8a6',
  'December': '#e11d48'
};

const MonthlySectorPicks = ({ onStockClick }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(null);
  const [currentMonth, setCurrentMonth] = useState('');
  
  // Sector stocks state
  const [selectedSector, setSelectedSector] = useState(null);
  const [sectorStocks, setSectorStocks] = useState([]);
  const [sectorLoading, setSectorLoading] = useState(false);
  const [sectorError, setSectorError] = useState(null);

  useEffect(() => {
    // Set current month
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];
    const now = new Date();
    setCurrentMonth(monthNames[now.getMonth()]);
    setSelectedMonth(monthNames[now.getMonth()]);
    
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/seasonality/month-vs-month`);
      if (!response.ok) throw new Error('Failed to fetch data');
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSectorClick = async (sector) => {
    // If clicking the same sector, close it
    if (selectedSector === sector) {
      setSelectedSector(null);
      setSectorStocks([]);
      return;
    }
    
    setSelectedSector(sector);
    setSectorLoading(true);
    setSectorError(null);
    setSectorStocks([]);
    
    try {
      const response = await fetch(`${API_BASE}/seasonality/sector/${encodeURIComponent(sector)}/stocks?top_n=5`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to load stocks');
      }
      const result = await response.json();
      setSectorStocks(result.stocks || []);
    } catch (err) {
      console.error('Error loading sector stocks:', err);
      setSectorError(err.message);
    } finally {
      setSectorLoading(false);
    }
  };

  const handleStockSelect = (symbol) => {
    if (onStockClick) {
      onStockClick(symbol);
    }
  };

  if (loading) {
    return (
      <div className="monthly-sector-picks loading">
        <div className="loading-spinner"></div>
        <span>Analyzing 10 years of sector performance...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="monthly-sector-picks error">
        <AlertCircle size={20} />
        <span>{error}</span>
      </div>
    );
  }

  if (!data) return null;

  const monthAnalysis = data.month_analysis || {};
  const months = Object.keys(monthAnalysis);

  return (
    <div className="monthly-sector-picks">
      <div className="section-header" onClick={() => setExpanded(!expanded)}>
        <div className="header-left">
          <Calendar size={20} />
          <h2>Monthly Sector Guide</h2>
          <span className="badge">10-Year Analysis</span>
        </div>
        <div className="header-right">
          {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </div>
      </div>

      {expanded && (
        <div className="section-content">
          {/* Current Month Highlight */}
          <div className="current-month-highlight">
            <div className="highlight-header">
              <Award size={18} />
              <span>Best Sectors for <strong>{currentMonth}</strong></span>
            </div>
            <div className="highlight-sectors">
              {monthAnalysis[currentMonth]?.slice(0, 3).map((sector, idx) => (
                <div 
                  key={sector.sector}
                  className={`highlight-sector rank-${idx + 1}`}
                  onClick={() => handleSectorClick(sector.sector)}
                >
                  <span className="rank">#{idx + 1}</span>
                  <span className="sector-name">{sector.sector}</span>
                  <span className={`return ${sector.avg_return >= 0 ? 'positive' : 'negative'}`}>
                    {sector.avg_return >= 0 ? '+' : ''}{sector.avg_return}%
                  </span>
                  <span className="win-rate">{sector.win_rate}% win</span>
                </div>
              ))}
            </div>
          </div>

          {/* Month Selector */}
          <div className="month-selector">
            <h4>Select Month to View Best Sectors</h4>
            <div className="month-grid">
              {months.map((month) => (
                <button
                  key={month}
                  className={`month-btn ${selectedMonth === month ? 'active' : ''} ${month === currentMonth ? 'current' : ''}`}
                  onClick={() => setSelectedMonth(month)}
                  style={{ 
                    '--month-color': MONTH_COLORS[month],
                    borderColor: selectedMonth === month ? MONTH_COLORS[month] : 'transparent'
                  }}
                >
                  {month.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>

          {/* Selected Month Details */}
          {selectedMonth && monthAnalysis[selectedMonth] && (
            <div className="selected-month-details">
              <h4>
                <TrendingUp size={16} />
                Top Sectors for {selectedMonth}
              </h4>
              <div className="sectors-table">
                <div className="table-header">
                  <span>Rank</span>
                  <span>Sector</span>
                  <span>Avg Return</span>
                  <span>Win Rate</span>
                </div>
                {monthAnalysis[selectedMonth].map((sector, idx) => (
                  <div 
                    key={sector.sector}
                    className={`table-row ${idx < 3 ? 'top-pick' : ''} ${selectedSector === sector.sector ? 'selected' : ''}`}
                    onClick={() => handleSectorClick(sector.sector)}
                  >
                    <span className={`rank rank-${idx + 1}`}>
                      {idx < 3 ? <Award size={14} /> : (idx + 1)}
                    </span>
                    <span className="sector">
                      {sector.sector}
                      {selectedSector === sector.sector && <ArrowRight size={12} className="sector-arrow" />}
                    </span>
                    <span className={`return ${sector.avg_return >= 0 ? 'positive' : 'negative'}`}>
                      {sector.avg_return >= 0 ? '+' : ''}{sector.avg_return}%
                    </span>
                    <span className="win-rate">
                      <div className="win-rate-bar">
                        <div 
                          className="win-rate-fill" 
                          style={{ width: `${sector.win_rate}%` }}
                        />
                      </div>
                      {sector.win_rate}%
                    </span>
                  </div>
                ))}
              </div>

              {/* Sector Stocks Panel */}
              {selectedSector && (
                <div className="sector-stocks-panel">
                  <div className="panel-header">
                    <h5>Top Stocks in {selectedSector}</h5>
                    <button className="close-panel" onClick={() => setSelectedSector(null)}>
                      <X size={16} />
                    </button>
                  </div>
                  
                  {sectorLoading && (
                    <div className="panel-loading">
                      <Loader size={20} className="spinning" />
                      <span>Loading stocks...</span>
                    </div>
                  )}
                  
                  {sectorError && (
                    <div className="panel-error">
                      <AlertCircle size={16} />
                      <span>{sectorError}</span>
                    </div>
                  )}
                  
                  {!sectorLoading && !sectorError && sectorStocks.length > 0 && (
                    <div className="sector-stocks-list">
                      {sectorStocks.map((stock, idx) => (
                        <div 
                          key={stock.symbol} 
                          className="sector-stock-item"
                          onClick={() => handleStockSelect(stock.symbol)}
                        >
                          <span className="stock-rank">#{idx + 1}</span>
                          <div className="stock-info">
                            <span className="stock-symbol">{stock.symbol}</span>
                            <span className="stock-metrics">
                              CAGR: {stock.cagr?.toFixed(1) || '-'}% | 
                              Sharpe: {stock.sharpe?.toFixed(2) || '-'}
                            </span>
                          </div>
                          <span className={`stock-return ${(stock.cagr || 0) >= 0 ? 'positive' : 'negative'}`}>
                            {stock.cagr ? `${stock.cagr >= 0 ? '+' : ''}${stock.cagr.toFixed(1)}%` : '-'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {!sectorLoading && !sectorError && sectorStocks.length === 0 && (
                    <div className="panel-empty">
                      No stocks found with current data
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Full Year Overview */}
          <div className="year-overview">
            <h4>Year at a Glance - Best Sector per Month</h4>
            <div className="year-grid">
              {months.map((month) => {
                const topSector = monthAnalysis[month]?.[0];
                return (
                  <div 
                    key={month}
                    className={`year-cell ${month === currentMonth ? 'current' : ''}`}
                    onClick={() => setSelectedMonth(month)}
                    style={{ '--month-color': MONTH_COLORS[month] }}
                  >
                    <span className="cell-month">{month.slice(0, 3)}</span>
                    <span className="cell-sector">{topSector?.sector || '-'}</span>
                    <span className={`cell-return ${topSector?.avg_return >= 0 ? 'positive' : 'negative'}`}>
                      {topSector ? `${topSector.avg_return >= 0 ? '+' : ''}${topSector.avg_return}%` : '-'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Insights */}
          <div className="insights-box">
            <Target size={16} />
            <div>
              <strong>Investment Insight:</strong> Based on 10 years of historical data, 
              sectors shown have historically outperformed in their respective months. 
              Consider allocating more to {monthAnalysis[currentMonth]?.[0]?.sector || 'top sectors'} this month.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MonthlySectorPicks;
