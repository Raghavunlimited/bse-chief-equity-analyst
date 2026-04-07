import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, AlertCircle, CheckCircle, XCircle, Filter } from 'lucide-react';
import { screenerAPI } from '../services/api';

function MarketRegimePanel({ onRegimeChange }) {
  const [regime, setRegime] = useState(null);
  const [sectorRotation, setSectorRotation] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMarketData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchMarketData = async () => {
    try {
      setLoading(true);
      const [regimeData, sectorData] = await Promise.all([
        screenerAPI.getMarketRegime().catch(() => null),
        screenerAPI.getSectorRotation(3).catch(() => null)
      ]);

      setRegime(regimeData);
      setSectorRotation(sectorData);

      if (onRegimeChange && regimeData) {
        onRegimeChange(regimeData);
      }
    } catch (err) {
      console.error('Failed to fetch market data:', err);
    } finally {
      setLoading(false);
    }
  };

  const getRegimeColor = () => {
    if (!regime) return '#6b7280';
    switch (regime.regime) {
      case 'BULL': return '#22c55e';
      case 'BEAR': return '#ef4444';
      case 'NEUTRAL': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  const getRegimeIcon = () => {
    if (!regime) return <AlertCircle size={20} />;
    switch (regime.regime) {
      case 'BULL': return <TrendingUp size={20} />;
      case 'BEAR': return <TrendingDown size={20} />;
      default: return <AlertCircle size={20} />;
    }
  };

  if (loading) {
    return (
      <div className="market-regime-panel loading">
        <div className="regime-loading">Loading market data...</div>
      </div>
    );
  }

  return (
    <div className="market-regime-panel">
      {/* Market Regime */}
      <div className="regime-section">
        <h3><Filter size={18} /> Market Regime</h3>
        <div className="regime-status" style={{ borderColor: getRegimeColor() }}>
          <div className="regime-icon" style={{ color: getRegimeColor() }}>
            {getRegimeIcon()}
          </div>
          <div className="regime-info">
            <span className="regime-label" style={{ color: getRegimeColor() }}>
              {regime?.regime || 'UNKNOWN'}
            </span>
            <span className="regime-trend">{regime?.nifty_trend || 'N/A'}</span>
          </div>
          <div className="regime-trading">
            {regime?.allow_trading ? (
              <span className="trading-allowed"><CheckCircle size={16} /> Trading OK</span>
            ) : (
              <span className="trading-blocked"><XCircle size={16} /> Stay Cash</span>
            )}
          </div>
        </div>
        {regime && (
          <div className="regime-details">
            <div className="regime-metric">
              <span>NIFTY Price</span>
              <span>₹{regime.nifty_price?.toFixed(0) || '-'}</span>
            </div>
            <div className="regime-metric">
              <span>SMA 20</span>
              <span>₹{regime.nifty_sma_20?.toFixed(0) || '-'}</span>
            </div>
            <div className="regime-metric">
              <span>SMA 50</span>
              <span>₹{regime.nifty_sma_50?.toFixed(0) || '-'}</span>
            </div>
            <div className="regime-metric">
              <span>20D Change</span>
              <span className={regime.nifty_20d_change >= 0 ? 'positive' : 'negative'}>
                {regime.nifty_20d_change?.toFixed(1) || '-'}%
              </span>
            </div>
          </div>
        )}
        <p className="regime-reason">{regime?.reason || ''}</p>
      </div>

      {/* Hot Sectors */}
      {sectorRotation && sectorRotation.hot_sectors && sectorRotation.hot_sectors.length > 0 && (
        <div className="sectors-section">
          <h3><TrendingUp size={18} /> Hot Sectors</h3>
          <div className="hot-sectors">
            {sectorRotation.hot_sectors.map((sector, idx) => (
              <div key={sector} className="hot-sector-badge">
                <span className="sector-rank">#{idx + 1}</span>
                <span className="sector-name">{sector}</span>
              </div>
            ))}
          </div>
          <p className="sector-note">
            Enhanced screener will prioritize stocks from these sectors
          </p>
        </div>
      )}
    </div>
  );
}

export default MarketRegimePanel;
