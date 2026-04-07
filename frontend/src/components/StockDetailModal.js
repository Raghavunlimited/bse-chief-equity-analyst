import React, { useState, useEffect } from 'react';
import { X, TrendingUp, TrendingDown, Target, BarChart2, Info, AlertTriangle, CheckCircle, Shield, Crosshair, DollarSign } from 'lucide-react';
import { screenerAPI } from '../services/api';
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Line,
  ReferenceLine
} from 'recharts';

function StockDetailModal({ symbol, onClose }) {
  const [stockData, setStockData] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [levelsData, setLevelsData] = useState(null);
  const [period, setPeriod] = useState('3M');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStockDetails();
    fetchChartData();
    fetchLevels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  useEffect(() => {
    fetchChartData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const fetchStockDetails = async () => {
    try {
      const data = await screenerAPI.getStockDetails(symbol);
      setStockData(data);
    } catch (err) {
      setError('Failed to load stock details');
      console.error(err);
    }
  };

  const fetchChartData = async () => {
    try {
      setLoading(true);
      const data = await screenerAPI.getChartData(symbol, period);
      setChartData(data);
    } catch (err) {
      console.error('Failed to load chart data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchLevels = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/stock/${symbol}/levels`);
      if (response.ok) {
        const data = await response.json();
        setLevelsData(data);
      }
    } catch (err) {
      console.error('Failed to load levels:', err);
    }
  };

  const formatPrice = (price) => {
    return `₹${price?.toFixed(2) || '0.00'}`;
  };

  const formatVolume = (vol) => {
    if (vol >= 10000000) return `${(vol / 10000000).toFixed(2)}Cr`;
    if (vol >= 100000) return `${(vol / 100000).toFixed(2)}L`;
    if (vol >= 1000) return `${(vol / 1000).toFixed(1)}K`;
    return vol;
  };

  if (error) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>{symbol}</h2>
            <button className="modal-close" onClick={onClose}><X size={24} /></button>
          </div>
          <div className="error">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{symbol}</h2>
            {stockData && (
              <div className="modal-price-info">
                <span className="current-price">{formatPrice(stockData.current_price)}</span>
                <span className={`price-change ${stockData.change_pct >= 0 ? 'positive' : 'negative'}`}>
                  {stockData.change_pct >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                  {stockData.change_pct?.toFixed(2)}%
                </span>
              </div>
            )}
          </div>
          <button className="modal-close" onClick={onClose}><X size={24} /></button>
        </div>

        {/* Period Selector */}
        <div className="period-selector">
          {['1W', '1M', '3M', '6M', '1Y'].map((p) => (
            <button
              key={p}
              className={`period-btn ${period === p ? 'active' : ''}`}
              onClick={() => setPeriod(p)}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Chart Section */}
        <div className="chart-section">
          {loading ? (
            <div className="chart-loading">Loading chart...</div>
          ) : chartData ? (
            <>
              {/* Price Chart */}
              <div className="chart-container">
                <h3><BarChart2 size={18} /> Price Chart ({period})</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={chartData.candles} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      tickFormatter={(val) => val.slice(5)}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      tickFormatter={(val) => `₹${val}`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af' }}
                      formatter={(value, name) => [formatPrice(value), name]}
                    />
                    {/* Support/Resistance Reference Lines */}
                    {levelsData && levelsData.support_levels.immediate[0] && (
                      <ReferenceLine y={levelsData.support_levels.immediate[0]} stroke="#22c55e" strokeDasharray="5 5" label={{ value: `S1: ₹${levelsData.support_levels.immediate[0]}`, fill: '#22c55e', fontSize: 10 }} />
                    )}
                    {levelsData && levelsData.resistance_levels.immediate[0] && (
                      <ReferenceLine y={levelsData.resistance_levels.immediate[0]} stroke="#ef4444" strokeDasharray="5 5" label={{ value: `R1: ₹${levelsData.resistance_levels.immediate[0]}`, fill: '#ef4444', fontSize: 10 }} />
                    )}
                    {levelsData && levelsData.targets.target_1 && (
                      <ReferenceLine y={levelsData.targets.target_1} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: `T1: ₹${levelsData.targets.target_1}`, fill: '#f59e0b', fontSize: 10 }} />
                    )}
                    <Bar dataKey="close" name="Close">
                      {chartData.candles.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                    {chartData.sma_20.length > 0 && (
                      <Line
                        type="monotone"
                        data={chartData.sma_20}
                        dataKey="value"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        dot={false}
                        name="SMA 20"
                      />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Volume Chart */}
              <div className="chart-container volume-chart">
                <h3>Volume</h3>
                <ResponsiveContainer width="100%" height={100}>
                  <ComposedChart data={chartData.volumes} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <XAxis dataKey="date" hide />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} tickFormatter={formatVolume} />
                    <Bar dataKey="volume">
                      {chartData.volumes.map((entry, index) => (
                        <Cell key={`vol-${index}`} fill={entry.color} opacity={0.7} />
                      ))}
                    </Bar>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Chart Stats */}
              <div className="chart-stats">
                <div className="stat-item">
                  <span className="stat-label">Period High</span>
                  <span className="stat-value positive">{formatPrice(chartData.stats.high)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Period Low</span>
                  <span className="stat-value negative">{formatPrice(chartData.stats.low)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Volume</span>
                  <span className="stat-value">{formatVolume(chartData.stats.avg_volume)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Days</span>
                  <span className="stat-value">{chartData.stats.total_days}</span>
                </div>
              </div>
            </>
          ) : (
            <div className="chart-loading">No chart data available</div>
          )}
        </div>

        {/* Indicators & Analysis */}
        {stockData && (
          <div className="analysis-section">
            {/* Technical Indicators */}
            <div className="indicators-panel">
              <h3><Info size={18} /> Technical Indicators</h3>
              <div className="indicators-grid">
                <div className="indicator-item">
                  <span className="indicator-label">RSI (14)</span>
                  <span className={`indicator-value ${
                    stockData.indicators.rsi_14 > 70 ? 'overbought' :
                    stockData.indicators.rsi_14 < 30 ? 'oversold' : ''
                  }`}>
                    {stockData.indicators.rsi_14?.toFixed(1) || '-'}
                  </span>
                </div>
                <div className="indicator-item">
                  <span className="indicator-label">SMA 20</span>
                  <span className="indicator-value">{formatPrice(stockData.indicators.sma_20)}</span>
                </div>
                <div className="indicator-item">
                  <span className="indicator-label">SMA 50</span>
                  <span className="indicator-value">{formatPrice(stockData.indicators.sma_50)}</span>
                </div>
                <div className="indicator-item">
                  <span className="indicator-label">ATR (14)</span>
                  <span className="indicator-value">{formatPrice(stockData.indicators.atr_14)}</span>
                </div>
                <div className="indicator-item">
                  <span className="indicator-label">ATR %</span>
                  <span className="indicator-value">{stockData.indicators.atr_pct?.toFixed(2)}%</span>
                </div>
                <div className="indicator-item">
                  <span className="indicator-label">Vol Ratio</span>
                  <span className={`indicator-value ${stockData.indicators.vol_ratio > 1.5 ? 'positive' : ''}`}>
                    {stockData.indicators.vol_ratio?.toFixed(2)}x
                  </span>
                </div>
              </div>
            </div>

            {/* Support/Resistance */}
            {stockData.support_resistance && (
              <div className="sr-panel">
                <h3><Target size={18} /> Support & Resistance</h3>
                <div className="sr-grid">
                  {stockData.support_resistance.resistance_levels?.slice(0, 2).map((level, idx) => (
                    <div key={`r-${idx}`} className="sr-item resistance">
                      <span>{level.type}</span>
                      <span>{formatPrice(level.level)}</span>
                    </div>
                  ))}
                  <div className="sr-item pivot">
                    <span>Pivot</span>
                    <span>{formatPrice(stockData.support_resistance.pivot_point)}</span>
                  </div>
                  {stockData.support_resistance.support_levels?.slice(0, 2).map((level, idx) => (
                    <div key={`s-${idx}`} className="sr-item support">
                      <span>{level.type}</span>
                      <span>{formatPrice(level.level)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Pros and Cons */}
            {stockData.pros_cons && (
              <div className="pros-cons-section">
                <div className="pros-panel">
                  <h3><CheckCircle size={18} /> Pros</h3>
                  <ul>
                    {stockData.pros_cons.pros.map((pro, idx) => (
                      <li key={idx} className="pro-item">{pro}</li>
                    ))}
                    {stockData.pros_cons.pros.length === 0 && (
                      <li className="empty-item">No significant positives detected</li>
                    )}
                  </ul>
                </div>
                <div className="cons-panel">
                  <h3><AlertTriangle size={18} /> Cons</h3>
                  <ul>
                    {stockData.pros_cons.cons.map((con, idx) => (
                      <li key={idx} className="con-item">{con}</li>
                    ))}
                    {stockData.pros_cons.cons.length === 0 && (
                      <li className="empty-item">No significant negatives detected</li>
                    )}
                  </ul>
                </div>
              </div>
            )}

            {/* Recommendation */}
            {stockData.recommendation && (
              <div className={`recommendation-panel ${stockData.recommendation.action.toLowerCase().replace(' ', '-')}`}>
                <div className="recommendation-header">
                  <h3>Recommendation</h3>
                  <span className="recommendation-badge">{stockData.recommendation.action}</span>
                </div>
                <p className="recommendation-reason">{stockData.recommendation.reason}</p>
                {stockData.recommendation.caution && (
                  <p className="recommendation-caution">
                    <AlertTriangle size={14} /> {stockData.recommendation.caution}
                  </p>
                )}
              </div>
            )}

            {/* Swing Trade Setup - Support/Resistance/Targets */}
            {levelsData && (
              <div className="swing-trade-panel">
                <h3><Crosshair size={18} /> Swing Trade Setup</h3>

                {/* Trade Recommendation */}
                <div className={`trade-recommendation ${levelsData.recommendation.action.toLowerCase().replace(' ', '-')}`}>
                  <div className="trade-rec-header">
                    <span className={`trade-action-badge ${levelsData.recommendation.action.toLowerCase().replace(' ', '-')}`}>
                      {levelsData.recommendation.action}
                    </span>
                    <span className="trade-trend">
                      Trend: <strong>{levelsData.trend.direction}</strong>
                    </span>
                  </div>
                  <p className="trade-reasoning">{levelsData.recommendation.reasoning}</p>
                </div>

                {/* Entry/Exit Levels Grid */}
                <div className="levels-grid">
                  {/* Support Levels */}
                  <div className="levels-section support-section">
                    <h4><Shield size={16} /> Support Levels</h4>
                    <div className="levels-list">
                      {levelsData.support_levels.immediate.map((level, idx) => (
                        <div key={`sup-${idx}`} className="level-item support">
                          <span className="level-label">S{idx + 1}</span>
                          <span className="level-value">{formatPrice(level)}</span>
                          <span className="level-distance">
                            {(((levelsData.current_price - level) / levelsData.current_price) * 100).toFixed(1)}% below
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Current Price */}
                  <div className="current-price-section">
                    <div className="price-indicator">
                      <span className="cpi-label">Current Price</span>
                      <span className="cpi-value">{formatPrice(levelsData.current_price)}</span>
                    </div>
                  </div>

                  {/* Resistance Levels */}
                  <div className="levels-section resistance-section">
                    <h4><TrendingUp size={16} /> Resistance Levels</h4>
                    <div className="levels-list">
                      {levelsData.resistance_levels.immediate.map((level, idx) => (
                        <div key={`res-${idx}`} className="level-item resistance">
                          <span className="level-label">R{idx + 1}</span>
                          <span className="level-value">{formatPrice(level)}</span>
                          <span className="level-distance">
                            {(((level - levelsData.current_price) / levelsData.current_price) * 100).toFixed(1)}% above
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Targets Section */}
                <div className="targets-section">
                  <h4><Target size={16} /> Price Targets</h4>
                  <div className="targets-grid">
                    <div className="target-card target-1">
                      <span className="target-label">Target 1</span>
                      <span className="target-price">{formatPrice(levelsData.targets.target_1)}</span>
                      <span className="target-gain positive">+{levelsData.targets.target_1_gain_pct}%</span>
                    </div>
                    <div className="target-card target-2">
                      <span className="target-label">Target 2</span>
                      <span className="target-price">{formatPrice(levelsData.targets.target_2)}</span>
                      <span className="target-gain positive">+{levelsData.targets.target_2_gain_pct}%</span>
                    </div>
                    <div className="target-card target-3">
                      <span className="target-label">Target 3</span>
                      <span className="target-price">{formatPrice(levelsData.targets.target_3)}</span>
                      <span className="target-gain positive">+{(((levelsData.targets.target_3 - levelsData.current_price) / levelsData.current_price) * 100).toFixed(2)}%</span>
                    </div>
                  </div>
                </div>

                {/* Stop Loss & Risk */}
                <div className="risk-section">
                  <h4><AlertTriangle size={16} /> Risk Management</h4>
                  <div className="risk-grid">
                    <div className="risk-card stop-loss">
                      <span className="risk-label">Stop Loss</span>
                      <span className="risk-value">{formatPrice(levelsData.stop_loss.recommended)}</span>
                      <span className="risk-pct negative">-{levelsData.stop_loss.risk_pct}%</span>
                    </div>
                    <div className="risk-card rr-ratio">
                      <span className="risk-label">Risk:Reward</span>
                      <span className={`risk-value ${levelsData.risk_reward.is_favorable ? 'favorable' : 'unfavorable'}`}>
                        1:{levelsData.risk_reward.ratio}
                      </span>
                      <span className="risk-note">{levelsData.risk_reward.is_favorable ? 'Favorable' : 'Poor'}</span>
                    </div>
                    <div className="risk-card position-size">
                      <span className="risk-label">Position Tip</span>
                      <span className="risk-note">{levelsData.recommendation.position_size_tip}</span>
                    </div>
                  </div>
                </div>

                {/* Quick Trade Summary */}
                <div className="trade-summary">
                  <h4><DollarSign size={16} /> Quick Trade Summary</h4>
                  <div className="summary-row">
                    <span>Entry Zone:</span>
                    <span>{levelsData.recommendation.entry_zone}</span>
                  </div>
                  <div className="summary-row">
                    <span>Stop Loss:</span>
                    <span className="negative">{formatPrice(levelsData.swing_trade_setup.stop_loss)}</span>
                  </div>
                  <div className="summary-row">
                    <span>Target 1:</span>
                    <span className="positive">{formatPrice(levelsData.swing_trade_setup.target_1)} (+{levelsData.swing_trade_setup.potential_gain_pct}%)</span>
                  </div>
                  <div className="summary-row">
                    <span>Max Risk:</span>
                    <span className="negative">{levelsData.swing_trade_setup.max_risk_pct}%</span>
                  </div>
                  <div className="summary-row">
                    <span>Holding Period:</span>
                    <span>{levelsData.swing_trade_setup.holding_period}</span>
                  </div>
                </div>

                {/* Moving Average Positions */}
                <div className="ma-positions">
                  <span className={`ma-badge ${levelsData.trend.price_vs_sma20 === 'ABOVE' ? 'above' : 'below'}`}>
                    {levelsData.trend.price_vs_sma20} SMA20
                  </span>
                  <span className={`ma-badge ${levelsData.trend.price_vs_sma50 === 'ABOVE' ? 'above' : 'below'}`}>
                    {levelsData.trend.price_vs_sma50} SMA50
                  </span>
                  <span className={`ma-badge ${levelsData.trend.price_vs_sma200 === 'ABOVE' ? 'above' : 'below'}`}>
                    {levelsData.trend.price_vs_sma200} SMA200
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default StockDetailModal;
