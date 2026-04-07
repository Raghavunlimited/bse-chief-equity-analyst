import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Target,
  BarChart2,
  Zap,
  Shield,
  Star
} from 'lucide-react';
import { screenerAPI } from '../services/api';

function SectorAnalysisPanel({ onSectorSelect }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedSector, setExpandedSector] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSectorAnalysis();
  }, []);

  const fetchSectorAnalysis = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await screenerAPI.getSectorAnalysis();
      setAnalysis(data);
    } catch (err) {
      console.error('Failed to fetch sector analysis:', err);
      setError('Failed to load sector analysis');
    } finally {
      setLoading(false);
    }
  };

  const getPhaseColor = (phase) => {
    switch (phase) {
      case 'LEADING': return '#22c55e';
      case 'IMPROVING': return '#3b82f6';
      case 'NEUTRAL': return '#f59e0b';
      case 'WEAKENING': return '#f97316';
      case 'LAGGING': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getPhaseIcon = (phase) => {
    switch (phase) {
      case 'LEADING': return <TrendingUp size={16} />;
      case 'IMPROVING': return <Zap size={16} />;
      case 'NEUTRAL': return <AlertCircle size={16} />;
      case 'WEAKENING': return <TrendingDown size={16} />;
      case 'LAGGING': return <TrendingDown size={16} />;
      default: return <AlertCircle size={16} />;
    }
  };

  const getRecommendationBadge = (rec) => {
    switch (rec) {
      case 'OVERWEIGHT':
        return <span className="rec-badge overweight"><Star size={12} /> Overweight</span>;
      case 'NEUTRAL':
        return <span className="rec-badge neutral">Neutral</span>;
      case 'UNDERWEIGHT':
        return <span className="rec-badge underweight">Underweight</span>;
      default:
        return null;
    }
  };

  const toggleSector = (sector) => {
    setExpandedSector(expandedSector === sector ? null : sector);
  };

  if (loading) {
    return (
      <div className="sector-analysis-panel loading">
        <div className="loading-text">Analyzing sectors...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sector-analysis-panel error">
        <AlertCircle size={20} />
        <span>{error}</span>
        <button onClick={fetchSectorAnalysis}>Retry</button>
      </div>
    );
  }

  if (!analysis || !analysis.sectors) {
    return null;
  }

  const { sectors, investment_summary, strategy_recommendation } = analysis;

  return (
    <div className="sector-analysis-panel">
      <div className="sector-header">
        <h2><BarChart2 size={24} /> Sector Rotation Analysis</h2>
        <button className="refresh-btn" onClick={fetchSectorAnalysis}>
          Refresh
        </button>
      </div>

      {/* Strategy Recommendation */}
      {strategy_recommendation && (
        <div className={`strategy-card ${strategy_recommendation.strategy.toLowerCase()}`}>
          <div className="strategy-header">
            <h3>Investment Strategy</h3>
            <span className="strategy-badge">{strategy_recommendation.strategy}</span>
          </div>
          <p className="strategy-description">{strategy_recommendation.description}</p>
          {strategy_recommendation.avoid && strategy_recommendation.avoid.length > 0 && (
            <p className="strategy-avoid">
              <Shield size={14} /> Avoid: {strategy_recommendation.avoid.join(', ')}
            </p>
          )}
        </div>
      )}

      {/* Rotation Signal */}
      {investment_summary?.sector_rotation_signal && (
        <div className={`rotation-signal ${investment_summary.sector_rotation_signal.signal.toLowerCase().replace(' ', '-')}`}>
          <div className="signal-header">
            <span className="signal-label">{investment_summary.sector_rotation_signal.signal}</span>
          </div>
          <p>{investment_summary.sector_rotation_signal.description}</p>
          <p className="signal-action">
            <Target size={14} /> {investment_summary.sector_rotation_signal.action}
          </p>
        </div>
      )}

      {/* Best Opportunities */}
      {investment_summary?.best_opportunities?.length > 0 && (
        <div className="best-opportunities">
          <h3><Star size={18} /> Top Opportunities</h3>
          <div className="opportunity-list">
            {investment_summary.best_opportunities.map((opp, idx) => (
              <div
                key={idx}
                className="opportunity-item"
                onClick={() => onSectorSelect && onSectorSelect(opp.symbol)}
              >
                <span className="opp-symbol">{opp.symbol}</span>
                <span className="opp-sector">{opp.sector}</span>
                <span className="opp-score">Score: {opp.score}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sector Cards */}
      <div className="sectors-list">
        <h3>Sector Rankings</h3>
        {sectors.map((sector, idx) => (
          <div
            key={sector.sector}
            className={`sector-card ${expandedSector === sector.sector ? 'expanded' : ''}`}
          >
            <div
              className="sector-card-header"
              onClick={() => toggleSector(sector.sector)}
            >
              <div className="sector-rank">#{idx + 1}</div>
              <div className="sector-main">
                <div className="sector-name-row">
                  <span className="sector-name">{sector.sector}</span>
                  {getRecommendationBadge(sector.recommendation)}
                </div>
                <div className="sector-phase" style={{ color: getPhaseColor(sector.phase) }}>
                  {getPhaseIcon(sector.phase)}
                  <span>{sector.phase}</span>
                  <span className="phase-desc">- {sector.phase_description}</span>
                </div>
              </div>
              <div className="sector-score">
                <div className="score-value">{sector.sector_score}</div>
                <div className="score-label">Score</div>
              </div>
              <div className="sector-expand">
                {expandedSector === sector.sector ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </div>
            </div>

            {expandedSector === sector.sector && (
              <div className="sector-details">
                {/* Metrics Grid */}
                <div className="metrics-grid">
                  <div className="metric-item">
                    <span className="metric-label">% Above SMA50</span>
                    <span className={`metric-value ${sector.metrics.pct_above_sma50 >= 50 ? 'positive' : 'negative'}`}>
                      {sector.metrics.pct_above_sma50}%
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">% Bullish Structure</span>
                    <span className={`metric-value ${sector.metrics.pct_bullish_structure >= 40 ? 'positive' : 'negative'}`}>
                      {sector.metrics.pct_bullish_structure}%
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Avg RSI</span>
                    <span className={`metric-value ${sector.metrics.avg_rsi >= 55 ? 'positive' : sector.metrics.avg_rsi <= 45 ? 'negative' : ''}`}>
                      {sector.metrics.avg_rsi}
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Avg Score</span>
                    <span className="metric-value">{sector.metrics.avg_stock_score}/20</span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">High Score Stocks</span>
                    <span className="metric-value">{sector.metrics.high_score_stocks}</span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Avg Vol Ratio</span>
                    <span className={`metric-value ${sector.metrics.avg_volume_ratio >= 1.2 ? 'positive' : ''}`}>
                      {sector.metrics.avg_volume_ratio}x
                    </span>
                  </div>
                </div>

                {/* Top Stocks */}
                {sector.top_stocks && sector.top_stocks.length > 0 && (
                  <div className="top-stocks">
                    <h4>Top Stocks in {sector.sector}</h4>
                    <div className="stock-list">
                      {sector.top_stocks.map((stock, idx) => (
                        <div
                          key={stock.symbol}
                          className="stock-item"
                          onClick={() => onSectorSelect && onSectorSelect(stock.symbol)}
                        >
                          <span className="stock-rank">#{idx + 1}</span>
                          <span className="stock-symbol">{stock.symbol}</span>
                          <span className={`stock-strength ${stock.strength.toLowerCase()}`}>
                            {stock.strength}
                          </span>
                          <span className="stock-score">Score: {stock.score}</span>
                          <span className="stock-rsi">RSI: {stock.rsi}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sector Info */}
                {sector.sector_info && (
                  <div className="sector-info">
                    <p className="sector-full-name">{sector.sector_info.name}</p>
                    <p className="sector-desc">{sector.sector_info.description}</p>
                    <p className="sector-chars">{sector.sector_info.characteristics}</p>
                  </div>
                )}

                {/* Recommendation */}
                <div className={`sector-recommendation ${sector.recommendation.toLowerCase()}`}>
                  <strong>{sector.recommendation}:</strong> {sector.recommendation_reason}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default SectorAnalysisPanel;
