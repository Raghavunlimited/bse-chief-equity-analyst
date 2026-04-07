import React, { useState, useEffect, useCallback } from 'react';
import { TrendingDown, TrendingUp, DollarSign, ChevronDown, ChevronRight, AlertCircle, RefreshCw, Target, BarChart3 } from 'lucide-react';

const SectorValuationPanel = ({ onStockClick }) => {
  const [valuationData, setValuationData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedSectors, setExpandedSectors] = useState({});
  const [viewMode, setViewMode] = useState('undervalued'); // 'undervalued', 'overvalued', 'all'

  const fetchValuationData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('http://localhost:8000/api/sector-valuation');
      if (!response.ok) throw new Error('Failed to fetch valuation data');
      const data = await response.json();
      setValuationData(data);
    } catch (err) {
      console.error('Error fetching valuation data:', err);
      setError('Failed to load valuation data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchValuationData();
  }, [fetchValuationData]);

  const toggleSector = (sector) => {
    setExpandedSectors(prev => ({
      ...prev,
      [sector]: !prev[sector]
    }));
  };

  const getValuationColor = (valuation) => {
    switch (valuation) {
      case 'DEEPLY_UNDERVALUED':
        return '#10b981'; // Green
      case 'UNDERVALUED':
        return '#22c55e';
      case 'FAIR_VALUE':
        return '#6b7280'; // Gray
      case 'OVERVALUED':
        return '#f59e0b'; // Orange
      case 'DEEPLY_OVERVALUED':
        return '#ef4444'; // Red
      default:
        return '#6b7280';
    }
  };

  const getValuationLabel = (valuation) => {
    switch (valuation) {
      case 'DEEPLY_UNDERVALUED':
        return 'Deeply Undervalued';
      case 'UNDERVALUED':
        return 'Undervalued';
      case 'FAIR_VALUE':
        return 'Fair Value';
      case 'OVERVALUED':
        return 'Overvalued';
      case 'DEEPLY_OVERVALUED':
        return 'Deeply Overvalued';
      default:
        return valuation;
    }
  };

  const StockCard = ({ stock }) => (
    <div
      className="valuation-stock-card"
      onClick={() => onStockClick && onStockClick(stock.symbol)}
    >
      <div className="stock-header">
        <span className="stock-symbol">{stock.symbol}</span>
        <span
          className="valuation-badge"
          style={{ backgroundColor: getValuationColor(stock.valuation) }}
        >
          {getValuationLabel(stock.valuation)}
        </span>
      </div>
      <div className="stock-metrics">
        <div className="metric">
          <span className="label">Price</span>
          <span className="value">{stock.close.toFixed(2)}</span>
        </div>
        <div className="metric">
          <span className="label">52W High</span>
          <span className="value">{stock.high_52w.toFixed(2)}</span>
        </div>
        <div className="metric">
          <span className="label">From High</span>
          <span className="value" style={{ color: stock.dist_from_high_pct > 20 ? '#22c55e' : '#ef4444' }}>
            -{stock.dist_from_high_pct.toFixed(1)}%
          </span>
        </div>
        <div className="metric">
          <span className="label">RSI</span>
          <span className="value" style={{
            color: stock.rsi < 35 ? '#22c55e' : stock.rsi > 70 ? '#ef4444' : '#6b7280'
          }}>
            {stock.rsi.toFixed(1)}
          </span>
        </div>
        <div className="metric">
          <span className="label">vs SMA200</span>
          <span className="value" style={{
            color: stock.price_vs_sma200_pct < 0 ? '#22c55e' : '#ef4444'
          }}>
            {stock.price_vs_sma200_pct > 0 ? '+' : ''}{stock.price_vs_sma200_pct.toFixed(1)}%
          </span>
        </div>
        <div className="metric">
          <span className="label">Score</span>
          <span className="value" style={{
            color: stock.valuation_score < 0 ? '#22c55e' : '#ef4444',
            fontWeight: 'bold'
          }}>
            {stock.valuation_score}
          </span>
        </div>
      </div>
    </div>
  );

  const SectorRow = ({ sectorData }) => {
    const isExpanded = expandedSectors[sectorData.sector];
    const stocksToShow = viewMode === 'undervalued'
      ? sectorData.undervalued
      : viewMode === 'overvalued'
        ? sectorData.overvalued
        : [...sectorData.undervalued, ...sectorData.overvalued];

    if (stocksToShow.length === 0 && viewMode !== 'all') return null;

    return (
      <div className="sector-valuation-row">
        <div
          className="sector-header"
          onClick={() => toggleSector(sectorData.sector)}
        >
          <div className="sector-info">
            {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            <span className="sector-name">{sectorData.sector}</span>
            <span className="stock-count">({sectorData.summary.total_stocks} stocks)</span>
          </div>
          <div className="sector-stats">
            <span className="stat undervalued">
              <TrendingDown size={14} />
              {sectorData.summary.undervalued_count} undervalued
            </span>
            <span className="stat fair">
              <DollarSign size={14} />
              {sectorData.summary.fair_value_count} fair
            </span>
            <span className="stat overvalued">
              <TrendingUp size={14} />
              {sectorData.summary.overvalued_count} overvalued
            </span>
          </div>
        </div>
        {isExpanded && (
          <div className="sector-stocks">
            {stocksToShow.length > 0 ? (
              <div className="stocks-grid">
                {stocksToShow.map(stock => (
                  <StockCard key={stock.symbol} stock={stock} />
                ))}
              </div>
            ) : (
              <p className="no-stocks">No stocks in this category</p>
            )}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="panel valuation-panel loading">
        <RefreshCw className="spinning" size={24} />
        <span>Loading valuation analysis...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel valuation-panel error">
        <AlertCircle size={24} />
        <span>{error}</span>
        <button onClick={fetchValuationData}>Retry</button>
      </div>
    );
  }

  if (!valuationData) return null;

  return (
    <div className="panel valuation-panel">
      <div className="panel-header">
        <div className="header-title">
          <Target size={24} />
          <h3>Sector Valuation Analysis</h3>
        </div>
        <div className="header-actions">
          <div className="view-toggle">
            <button
              className={viewMode === 'undervalued' ? 'active' : ''}
              onClick={() => setViewMode('undervalued')}
            >
              <TrendingDown size={14} /> Undervalued
            </button>
            <button
              className={viewMode === 'overvalued' ? 'active' : ''}
              onClick={() => setViewMode('overvalued')}
            >
              <TrendingUp size={14} /> Overvalued
            </button>
            <button
              className={viewMode === 'all' ? 'active' : ''}
              onClick={() => setViewMode('all')}
            >
              <BarChart3 size={14} /> All
            </button>
          </div>
          <button className="refresh-btn" onClick={fetchValuationData}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Market Summary */}
      <div className="market-summary">
        <div className="summary-card">
          <span className="label">Total Analyzed</span>
          <span className="value">{valuationData.market_summary.total_stocks_analyzed}</span>
        </div>
        <div className="summary-card undervalued">
          <span className="label">Undervalued</span>
          <span className="value">{valuationData.market_summary.undervalued_count}</span>
          <span className="pct">
            ({((valuationData.market_summary.undervalued_count / valuationData.market_summary.total_stocks_analyzed) * 100).toFixed(0)}%)
          </span>
        </div>
        <div className="summary-card fair">
          <span className="label">Fair Value</span>
          <span className="value">{valuationData.market_summary.fair_value_count}</span>
        </div>
        <div className="summary-card overvalued">
          <span className="label">Overvalued</span>
          <span className="value">{valuationData.market_summary.overvalued_count}</span>
        </div>
        <div className={`summary-card sentiment ${valuationData.market_summary.market_sentiment.toLowerCase()}`}>
          <span className="label">Market Sentiment</span>
          <span className="value">{valuationData.market_summary.market_sentiment}</span>
        </div>
      </div>

      {/* Methodology Info */}
      <div className="methodology-info">
        <details>
          <summary>How valuation is calculated</summary>
          <ul>
            {valuationData.methodology.factors.map((factor, i) => (
              <li key={i}>{factor}</li>
            ))}
          </ul>
          <p><strong>Undervalued:</strong> {valuationData.methodology.undervalued_criteria}</p>
          <p><strong>Overvalued:</strong> {valuationData.methodology.overvalued_criteria}</p>
        </details>
      </div>

      {/* Sector List */}
      <div className="sectors-list">
        {valuationData.sectors
          .filter(s => {
            if (viewMode === 'undervalued') return s.undervalued.length > 0;
            if (viewMode === 'overvalued') return s.overvalued.length > 0;
            return true;
          })
          .map(sector => (
            <SectorRow key={sector.sector} sectorData={sector} />
          ))}
      </div>

      <div className="panel-footer">
        <p className="tip">
          Combine with <strong>Sector Rotation</strong> analysis: Look for undervalued stocks
          in sectors showing rotation momentum for wealth building opportunities.
        </p>
      </div>
    </div>
  );
};

export default SectorValuationPanel;
