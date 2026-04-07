import React from 'react';
import { TrendingUp, Target, Shield, ExternalLink, Zap, Activity } from 'lucide-react';

function CandidateCard({ candidate, rank, onClick, showPatterns }) {
  const { symbol, score, close_price, entry_price, stop_loss, target_price, risk_reward, position_size, metadata } = candidate;

  const expectedGain = metadata?.expected_gain_pct || metadata?.reward_pct || 0;
  const riskPct = metadata?.risk_pct || 0;
  const rsi = metadata?.rsi_14 || 0;
  const atrPct = metadata?.atr_pct || 0;
  const strength = metadata?.strength || candidate.signal_strength || 'MODERATE';

  // Pattern-related data for ultimate mode
  const patterns = metadata?.patterns || '';
  const patternScore = metadata?.pattern_score || 0;
  const trendStrength = metadata?.trend_strength || 0;
  const supertrend = metadata?.supertrend || 'N/A';
  const adx = metadata?.adx || 0;
  const volRatio = metadata?.vol_ratio || 1;
  const relativeStrength = metadata?.relative_strength || 1;
  const sector = candidate?.sector || metadata?.sector || 'Unknown';

  const getStrengthColor = () => {
    switch (strength) {
      case 'EXCELLENT': return '#10b981';
      case 'STRONG': return '#22c55e';
      case 'GOOD': return '#84cc16';
      case 'MODERATE': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  // Calculate score display based on mode
  const displayScore = showPatterns ? `${score}%` : `${score}/20`;

  return (
    <div className="candidate-card" onClick={() => onClick && onClick(symbol)}>
      <div className="candidate-header">
        <div>
          <span style={{ color: '#9ca3af', fontSize: '0.9rem', marginRight: '0.5rem' }}>#{rank}</span>
          <span className="candidate-symbol">{symbol}</span>
          <ExternalLink size={14} className="view-details-icon" />
        </div>
        <div className="candidate-score" style={{ backgroundColor: getStrengthColor() + '20', color: getStrengthColor() }}>
          Score: {displayScore}
        </div>
      </div>

      <div className="strength-badge" style={{ color: getStrengthColor(), borderColor: getStrengthColor() }}>
        {strength}
        {sector !== 'Unknown' && <span style={{ marginLeft: '0.5rem', opacity: 0.8 }}>| {sector}</span>}
      </div>

      {/* Pattern Info for Ultimate Mode */}
      {showPatterns && patterns && patterns !== 'No clear pattern' && (
        <div className="pattern-info">
          <Zap size={14} style={{ marginRight: '0.25rem' }} />
          <span>{patterns}</span>
        </div>
      )}

      {showPatterns && (
        <div className="trend-indicators">
          <div className={`trend-badge ${supertrend === 'BULLISH' ? 'bullish' : 'bearish'}`}>
            <Activity size={12} /> {supertrend}
          </div>
          <div className="trend-badge">
            ADX: {adx.toFixed ? adx.toFixed(0) : adx}
          </div>
          <div className="trend-badge">
            Trend: {trendStrength}/10
          </div>
        </div>
      )}

      <div className="candidate-details">
        <div className="detail-item">
          <div className="detail-label">Current Price</div>
          <div className="detail-value">₹{close_price?.toFixed(2)}</div>
        </div>

        <div className="detail-item">
          <div className="detail-label">
            <Target size={14} style={{ display: 'inline', marginRight: '0.25rem' }} />
            Entry Price
          </div>
          <div className="detail-value">₹{entry_price?.toFixed(2)}</div>
        </div>

        <div className="detail-item">
          <div className="detail-label">
            <Shield size={14} style={{ display: 'inline', marginRight: '0.25rem' }} />
            Stop Loss
          </div>
          <div className="detail-value negative">₹{stop_loss?.toFixed(2)}</div>
          <div style={{ fontSize: '0.85rem', color: '#f87171' }}>-{riskPct?.toFixed ? riskPct.toFixed(2) : riskPct}%</div>
        </div>

        <div className="detail-item">
          <div className="detail-label">
            <TrendingUp size={14} style={{ display: 'inline', marginRight: '0.25rem' }} />
            Target Price
          </div>
          <div className="detail-value positive">₹{target_price?.toFixed(2)}</div>
          <div style={{ fontSize: '0.85rem', color: '#34d399' }}>+{expectedGain?.toFixed ? expectedGain.toFixed(2) : expectedGain}%</div>
        </div>

        <div className="detail-item">
          <div className="detail-label">Risk:Reward</div>
          <div className="detail-value">1:{risk_reward?.toFixed(2)}</div>
        </div>

        <div className="detail-item">
          <div className="detail-label">Position Size</div>
          <div className="detail-value">{position_size} shares</div>
        </div>
      </div>

      <div className="candidate-metadata">
        <div className="metadata-badge">
          RSI: {rsi?.toFixed ? rsi.toFixed(1) : rsi}
        </div>
        {showPatterns ? (
          <>
            <div className="metadata-badge">
              Vol: {volRatio?.toFixed ? volRatio.toFixed(1) : volRatio}x
            </div>
            <div className="metadata-badge">
              RS: {relativeStrength?.toFixed ? relativeStrength.toFixed(2) : relativeStrength}
            </div>
          </>
        ) : (
          <>
            <div className="metadata-badge">
              ATR: {atrPct?.toFixed ? atrPct.toFixed(2) : atrPct}%
            </div>
            <div className="metadata-badge">
              Investment: ₹{(entry_price * position_size)?.toLocaleString('en-IN')}
            </div>
          </>
        )}
      </div>

      <div className="click-hint">Click to view chart & analysis</div>
    </div>
  );
}

export default CandidateCard;
