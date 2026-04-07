import React, { useState, useEffect } from 'react';
import { Calendar, ChevronDown, ChevronUp, Info, DollarSign, BarChart3, Target, AlertCircle } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const SeasonalityHeatmap = ({ onStockClick }) => {
  const [heatmapData, setHeatmapData] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const [selectedSector, setSelectedSector] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(null);
  const [sectorStocks, setSectorStocks] = useState(null);
  const [stockFinancials, setStockFinancials] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showValidation, setShowValidation] = useState(false);
  const [validationData, setValidationData] = useState(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    fetchHeatmapData();
    fetchRecommendations();
  }, []);

  const fetchHeatmapData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/seasonality/heatmap`);
      if (!response.ok) throw new Error('Failed to fetch heatmap data');
      const data = await response.json();
      setHeatmapData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchRecommendations = async () => {
    try {
      const response = await fetch(`${API_BASE}/seasonality/recommendations`);
      if (!response.ok) throw new Error('Failed to fetch recommendations');
      const data = await response.json();
      setRecommendations(data);
    } catch (err) {
      console.error('Error fetching recommendations:', err);
    }
  };

  const fetchSectorStocks = async (sector, includeFinancials = false) => {
    try {
      const response = await fetch(
        `${API_BASE}/seasonality/sector/${encodeURIComponent(sector)}/stocks?top_n=5&include_financials=${includeFinancials}`
      );
      if (!response.ok) throw new Error('Failed to fetch sector stocks');
      const data = await response.json();
      setSectorStocks(data);
    } catch (err) {
      console.error('Error fetching sector stocks:', err);
    }
  };

  const fetchStockFinancials = async (symbol) => {
    try {
      const response = await fetch(`${API_BASE}/seasonality/stock/${symbol}/financials`);
      if (!response.ok) throw new Error('Failed to fetch financials');
      const data = await response.json();
      setStockFinancials(data);
    } catch (err) {
      console.error('Error fetching financials:', err);
    }
  };

  const fetchValidation = async () => {
    try {
      const response = await fetch(`${API_BASE}/seasonality/validate`);
      if (!response.ok) throw new Error('Failed to validate');
      const data = await response.json();
      setValidationData(data);
      setShowValidation(true);
    } catch (err) {
      console.error('Error validating:', err);
    }
  };

  const handleCellClick = (sector, month) => {
    setSelectedSector(sector);
    setSelectedMonth(month);
    fetchSectorStocks(sector, false);
    setStockFinancials(null);
  };

  const handleStockSelect = (symbol) => {
    fetchStockFinancials(symbol);
    if (onStockClick) {
      onStockClick(symbol);
    }
  };

  const getReturnColor = (value) => {
    if (value >= 5) return '#22c55e';
    if (value >= 3) return '#4ade80';
    if (value >= 1) return '#86efac';
    if (value >= 0) return '#bbf7d0';
    if (value >= -1) return '#fecaca';
    if (value >= -3) return '#f87171';
    if (value >= -5) return '#ef4444';
    return '#dc2626';
  };

  const getReturnBgColor = (value) => {
    if (value >= 5) return 'rgba(34, 197, 94, 0.3)';
    if (value >= 3) return 'rgba(74, 222, 128, 0.25)';
    if (value >= 1) return 'rgba(134, 239, 172, 0.2)';
    if (value >= 0) return 'rgba(187, 247, 208, 0.15)';
    if (value >= -1) return 'rgba(254, 202, 202, 0.2)';
    if (value >= -3) return 'rgba(248, 113, 113, 0.25)';
    if (value >= -5) return 'rgba(239, 68, 68, 0.3)';
    return 'rgba(220, 38, 38, 0.35)';
  };

  if (loading) {
    return <div className="seasonality-loading">Loading 10-year seasonality data...</div>;
  }

  if (error) {
    return <div className="seasonality-error">{error}</div>;
  }

  if (!heatmapData) {
    return null;
  }

  const months = heatmapData.months || [];
  const sectors = heatmapData.sectors || [];
  const heatmap = heatmapData.heatmap || {};

  return (
    <div className="seasonality-container">
      <div className="seasonality-header" onClick={() => setExpanded(!expanded)}>
        <h3>
          <Calendar size={20} />
          Sector Seasonality Heatmap (10-Year Analysis)
        </h3>
        <div className="seasonality-header-right">
          <button className="validate-btn" onClick={(e) => { e.stopPropagation(); fetchValidation(); }}>
            <Info size={14} /> Validate Stats
          </button>
          {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </div>
      </div>

      {expanded && (
        <div className="seasonality-content">
          {/* Current Month Recommendations */}
          {recommendations && (
            <div className="seasonality-recommendations">
              <h4>
                <Target size={16} />
                Best Sectors for {recommendations.month} (Based on 10-Year History)
              </h4>
              <div className="top-sectors-list">
                {recommendations.top_sectors?.map((sector, idx) => (
                  <div
                    key={sector.sector}
                    className={`top-sector-card rank-${idx + 1}`}
                    onClick={() => handleCellClick(sector.sector, recommendations.month)}
                  >
                    <div className="sector-rank">#{idx + 1}</div>
                    <div className="sector-name">{sector.sector}</div>
                    <div className="sector-stats">
                      <span className={`sector-return ${sector.avg_return >= 0 ? 'positive' : 'negative'}`}>
                        {sector.avg_return >= 0 ? '+' : ''}{sector.avg_return}%
                      </span>
                      <span className="sector-winrate">{sector.win_rate}% win rate</span>
                    </div>
                  </div>
                ))}
              </div>
              <p className="recommendation-note">{recommendations.recommendation_summary}</p>
            </div>
          )}

          {/* Heatmap Grid */}
          <div className="heatmap-wrapper">
            <div className="heatmap-table-container">
              <table className="heatmap-table">
                <thead>
                  <tr>
                    <th className="sector-header">Sector</th>
                    {months.map(month => (
                      <th key={month} className="month-header">{month}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sectors.map(sector => (
                    <tr key={sector}>
                      <td className="sector-name-cell">{sector}</td>
                      {months.map(month => {
                        const cellData = heatmap[sector]?.[month];
                        const avgReturn = cellData?.avg_return || 0;
                        const winRate = cellData?.win_rate || 0;

                        return (
                          <td
                            key={`${sector}-${month}`}
                            className={`heatmap-cell ${selectedSector === sector && selectedMonth === month ? 'selected' : ''}`}
                            style={{
                              backgroundColor: getReturnBgColor(avgReturn),
                              color: getReturnColor(avgReturn)
                            }}
                            onClick={() => handleCellClick(sector, month)}
                            title={`${sector} in ${month}: Avg ${avgReturn}%, Win Rate ${winRate}%`}
                          >
                            <div className="cell-value">
                              {avgReturn >= 0 ? '+' : ''}{avgReturn.toFixed(1)}%
                            </div>
                            <div className="cell-winrate">{winRate}%</div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Data Info */}
          <div className="heatmap-info">
            <span>Data: {heatmapData.data_info?.date_range?.start} to {heatmapData.data_info?.date_range?.end}</span>
            <span>{heatmapData.data_info?.total_stocks} stocks across {heatmapData.data_info?.total_sectors} sectors</span>
          </div>

          {/* Selected Sector Stocks */}
          {selectedSector && sectorStocks && (
            <div className="sector-stocks-panel">
              <h4>
                <BarChart3 size={16} />
                Top Stocks in {selectedSector}
                {selectedMonth && <span className="selected-month">({selectedMonth})</span>}
              </h4>
              <p className="criteria-note">{sectorStocks.criteria}</p>

              <div className="stocks-grid">
                {sectorStocks.stocks?.map((stock, idx) => (
                  <div
                    key={stock.symbol}
                    className={`stock-card ${stock.is_undervalued ? 'undervalued' : ''}`}
                    onClick={() => handleStockSelect(stock.symbol)}
                  >
                    <div className="stock-header">
                      <span className="stock-rank">#{idx + 1}</span>
                      <span className="stock-symbol">{stock.symbol}</span>
                      {stock.is_undervalued && (
                        <span className="undervalued-badge">Undervalued</span>
                      )}
                    </div>
                    <div className="stock-price">Rs {stock.current_price}</div>
                    <div className="stock-metrics">
                      <div className="metric">
                        <span className="metric-label">10Y CAGR</span>
                        <span className={`metric-value ${stock.cagr >= 0 ? 'positive' : 'negative'}`}>
                          {stock.cagr >= 0 ? '+' : ''}{stock.cagr}%
                        </span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">Win Rate</span>
                        <span className="metric-value">{stock.win_rate}%</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">Sharpe</span>
                        <span className="metric-value">{stock.sharpe_ratio}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">52W High Dist</span>
                        <span className={`metric-value ${stock.dist_from_52w_high > 20 ? 'warning' : ''}`}>
                          -{stock.dist_from_52w_high}%
                        </span>
                      </div>
                    </div>
                    <div className="stock-score">
                      Score: {stock.composite_score}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stock Financials */}
          {stockFinancials && !stockFinancials.error && (
            <div className="financials-panel">
              <h4>
                <DollarSign size={16} />
                {stockFinancials.company_name || stockFinancials.symbol} - Financial Data
              </h4>
              <div className="financials-grid">
                <div className="financial-item">
                  <span className="fin-label">Market Cap</span>
                  <span className="fin-value">Rs {stockFinancials.market_cap_cr} Cr</span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">P/E Ratio</span>
                  <span className={`fin-value ${stockFinancials.pe_ratio > 30 ? 'warning' : stockFinancials.pe_ratio < 15 ? 'good' : ''}`}>
                    {stockFinancials.pe_ratio || 'N/A'}
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">P/B Ratio</span>
                  <span className={`fin-value ${stockFinancials.pb_ratio > 5 ? 'warning' : stockFinancials.pb_ratio < 2 ? 'good' : ''}`}>
                    {stockFinancials.pb_ratio || 'N/A'}
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">ROE</span>
                  <span className={`fin-value ${stockFinancials.roe > 15 ? 'good' : stockFinancials.roe < 10 ? 'warning' : ''}`}>
                    {stockFinancials.roe}%
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Dividend Yield</span>
                  <span className="fin-value">{stockFinancials.dividend_yield}%</span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">EPS</span>
                  <span className="fin-value">Rs {stockFinancials.eps}</span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Debt/Equity</span>
                  <span className={`fin-value ${stockFinancials.debt_to_equity > 1 ? 'warning' : 'good'}`}>
                    {stockFinancials.debt_to_equity || 'N/A'}
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Profit Margin</span>
                  <span className={`fin-value ${stockFinancials.profit_margin > 10 ? 'good' : ''}`}>
                    {stockFinancials.profit_margin}%
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Revenue Growth</span>
                  <span className={`fin-value ${stockFinancials.revenue_growth > 10 ? 'good' : stockFinancials.revenue_growth < 0 ? 'warning' : ''}`}>
                    {stockFinancials.revenue_growth}%
                  </span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Book Value</span>
                  <span className="fin-value">Rs {stockFinancials.book_value}</span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">52W Range</span>
                  <span className="fin-value">{stockFinancials['52_week_low']} - {stockFinancials['52_week_high']}</span>
                </div>
                <div className="financial-item">
                  <span className="fin-label">Recommendation</span>
                  <span className={`fin-value recommendation ${stockFinancials.recommendation}`}>
                    {stockFinancials.recommendation?.toUpperCase() || 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Validation Modal */}
          {showValidation && validationData && (
            <div className="validation-modal">
              <div className="validation-content">
                <h4>
                  <AlertCircle size={16} />
                  Data Validation Results
                  <span className={`validation-status ${validationData.overall_status === 'VALID' ? 'valid' : 'review'}`}>
                    {validationData.overall_status}
                  </span>
                </h4>
                <button className="close-btn" onClick={() => setShowValidation(false)}>x</button>

                <div className="validation-summary">
                  <div className="val-item">
                    <span>Total Records:</span>
                    <span>{validationData.total_records?.toLocaleString()}</span>
                  </div>
                  <div className="val-item">
                    <span>Unique Stocks:</span>
                    <span>{validationData.unique_stocks}</span>
                  </div>
                  <div className="val-item">
                    <span>Unique Sectors:</span>
                    <span>{validationData.unique_sectors}</span>
                  </div>
                  <div className="val-item">
                    <span>Years Covered:</span>
                    <span>{validationData.years_covered}</span>
                  </div>
                </div>

                <h5>Sanity Checks</h5>
                <div className="sanity-checks">
                  {validationData.sanity_checks?.map((check, idx) => (
                    <div key={idx} className={`check-item ${check.passed ? 'passed' : 'failed'}`}>
                      <span className="check-icon">{check.passed ? 'ok' : 'warning'}</span>
                      <span className="check-name">{check.check}</span>
                      <span className="check-value">{typeof check.value === 'number' ? check.value.toFixed(2) : check.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SeasonalityHeatmap;
