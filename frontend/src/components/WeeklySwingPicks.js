import React, { useState, useEffect, useCallback } from 'react';
import { Target, TrendingUp, TrendingDown, Shield, AlertTriangle, DollarSign, Calendar, Zap, RefreshCw, Award, ChevronDown, ChevronUp, Clock, Users, BarChart3, FileText, CheckCircle, XCircle, Activity } from 'lucide-react';

const WeeklySwingPicks = ({ onStockClick }) => {
  const [picksData, setPicksData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedPick, setExpandedPick] = useState(null);
  const [activeTab, setActiveTab] = useState({});

  const fetchWeeklyPicks = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/weekly-swing-picks');
      if (!response.ok) throw new Error('Failed to fetch weekly picks');
      const data = await response.json();
      setPicksData(data);
      if (data.picks && data.picks.length > 0) {
        setExpandedPick(data.picks[0].symbol);
        const tabs = {};
        data.picks.forEach(p => { tabs[p.symbol] = 'trade'; });
        setActiveTab(tabs);
      }
    } catch (err) {
      setError(err.message);
      console.error('Error fetching weekly picks:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWeeklyPicks();
  }, [fetchWeeklyPicks]);

  const formatPrice = (price) => `₹${price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}`;

  const toggleExpand = (symbol) => {
    setExpandedPick(expandedPick === symbol ? null : symbol);
  };

  const switchTab = (symbol, tab) => {
    setActiveTab(prev => ({ ...prev, [symbol]: tab }));
  };

  const getConfidenceBadgeClass = (confidence) => {
    switch (confidence) {
      case 'HIGH': return 'confidence-high';
      case 'MEDIUM': return 'confidence-medium';
      default: return 'confidence-moderate';
    }
  };

  const getTagColor = (tag) => {
    switch (tag) {
      case 'LONG-TERM': return '#22c55e';
      case 'SHORT-TERM': return '#3b82f6';
      case 'AVOID': return '#ef4444';
      default: return '#94a3b8';
    }
  };

  const renderScoreBar = (value, max = 10) => {
    const pct = (value / max) * 100;
    const color = pct >= 70 ? '#22c55e' : pct >= 50 ? '#eab308' : pct >= 30 ? '#f97316' : '#ef4444';
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%' }}>
        <div style={{ flex: 1, height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '4px', transition: 'width 0.5s' }} />
        </div>
        <span style={{ fontWeight: 700, fontSize: '14px', color, minWidth: '30px', textAlign: 'right' }}>{value}</span>
      </div>
    );
  };

  const renderAnalystReport = (pick) => {
    const report = pick.analyst_report;
    if (!report) return <div className="no-report">Analyst report loading...</div>;

    const tab = activeTab[pick.symbol] || 'trade';

    return (
      <div className="analyst-report-section">
        {/* Tab Navigation */}
        <div className="report-tabs">
          <button className={`report-tab ${tab === 'trade' ? 'active' : ''}`} onClick={() => switchTab(pick.symbol, 'trade')}>
            <Target size={14} /> Trade Setup
          </button>
          <button className={`report-tab ${tab === 'scorecard' ? 'active' : ''}`} onClick={() => switchTab(pick.symbol, 'scorecard')}>
            <BarChart3 size={14} /> Scorecard
          </button>
          <button className={`report-tab ${tab === 'analysis' ? 'active' : ''}`} onClick={() => switchTab(pick.symbol, 'analysis')}>
            <FileText size={14} /> Analysis
          </button>
          <button className={`report-tab ${tab === 'scenarios' ? 'active' : ''}`} onClick={() => switchTab(pick.symbol, 'scenarios')}>
            <Activity size={14} /> Scenarios
          </button>
        </div>

        {/* Trade Setup Tab */}
        {tab === 'trade' && (
          <div className="tab-content">
            <div className="trade-setup-section">
              <h4><Target size={16} /> Trade Setup</h4>
              <div className="setup-grid">
                <div className="setup-card entry">
                  <span className="setup-label">Entry Zone</span>
                  <span className="setup-value">{pick.trade_setup.entry_zone}</span>
                </div>
                <div className="setup-card stop-loss">
                  <span className="setup-label">Stop Loss</span>
                  <span className="setup-value negative">{formatPrice(pick.trade_setup.stop_loss)}</span>
                  <span className="setup-pct">-{pick.trade_setup.stop_loss_pct}%</span>
                </div>
                <div className="setup-card target target-1">
                  <span className="setup-label">Target 1</span>
                  <span className="setup-value positive">{formatPrice(pick.trade_setup.target_1)}</span>
                  <span className="setup-pct">+{pick.trade_setup.target_1_pct}%</span>
                </div>
                <div className="setup-card target target-2">
                  <span className="setup-label">Target 2</span>
                  <span className="setup-value positive">{formatPrice(pick.trade_setup.target_2)}</span>
                  <span className="setup-pct">+{pick.trade_setup.target_2_pct}%</span>
                </div>
                <div className="setup-card target target-3">
                  <span className="setup-label">Target 3</span>
                  <span className="setup-value positive">{formatPrice(pick.trade_setup.target_3)}</span>
                  <span className="setup-pct">+{pick.trade_setup.target_3_pct}%</span>
                </div>
                <div className="setup-card rr">
                  <span className="setup-label">Risk:Reward</span>
                  <span className={`setup-value ${pick.trade_setup.risk_reward_ratio >= 2 ? 'favorable' : ''}`}>
                    1:{pick.trade_setup.risk_reward_ratio}
                  </span>
                </div>
              </div>

              <div className="technical-row">
                <span className="tech-item">RSI: <strong>{pick.technical.rsi}</strong></span>
                <span className="tech-item">Vol: <strong>{pick.technical.vol_ratio}x</strong></span>
                {pick.technical.atr_pct && <span className="tech-item">ATR: <strong>{pick.technical.atr_pct}%</strong></span>}
              </div>

              <div className="exit-strategy">
                <Shield size={14} />
                <span>{pick.trade_setup.exit_strategy}</span>
              </div>
              <div className="holding-period">
                <DollarSign size={14} />
                <span>Hold: {pick.trade_setup.holding_period}</span>
                <span className="position-tip">{pick.trade_setup.position_size_tip}</span>
              </div>

              {/* Invalidation from analyst report */}
              {report.plan && report.plan.invalidation && (
                <div className="invalidation-section">
                  <h5><AlertTriangle size={14} /> Invalidation (What Proves Thesis Wrong)</h5>
                  <p>{report.plan.invalidation}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Scorecard Tab */}
        {tab === 'scorecard' && report.scorecard && (
          <div className="tab-content">
            <div className="scorecard-section">
              {/* Classification Tag */}
              {report.classification && (
                <div className="classification-banner" style={{ borderLeftColor: getTagColor(report.classification.tag) }}>
                  <span className="classification-tag" style={{ color: getTagColor(report.classification.tag) }}>
                    {report.classification.tag}
                  </span>
                  <span className="classification-reason">{report.classification.reasoning}</span>
                </div>
              )}

              <h4><BarChart3 size={16} /> Analyst Scorecard (0-10)</h4>
              <div className="scorecard-grid">
                <div className="score-row">
                  <span className="score-label">Long-Term</span>
                  {renderScoreBar(report.scorecard.long_term)}
                </div>
                <div className="score-row">
                  <span className="score-label">Short-Term</span>
                  {renderScoreBar(report.scorecard.short_term)}
                </div>
                <div className="score-row">
                  <span className="score-label">Risk (10=safe)</span>
                  {renderScoreBar(report.scorecard.risk)}
                </div>
                <div className="score-row">
                  <span className="score-label">Valuation</span>
                  {renderScoreBar(report.scorecard.valuation)}
                </div>
                <div className="score-row">
                  <span className="score-label">Quality</span>
                  {renderScoreBar(report.scorecard.quality)}
                </div>
                <div className="score-row composite">
                  <span className="score-label"><strong>Composite</strong></span>
                  {renderScoreBar(report.scorecard.composite)}
                </div>
              </div>

              {/* Fundamentals Snapshot */}
              {report.fundamentals_snapshot && (
                <div className="fundamentals-snapshot">
                  <h5>Key Fundamentals</h5>
                  <div className="snapshot-grid">
                    {report.fundamentals_snapshot.pe_ratio && <div className="snap-item"><span>P/E</span><strong>{report.fundamentals_snapshot.pe_ratio}</strong></div>}
                    {report.fundamentals_snapshot.pb_ratio && <div className="snap-item"><span>P/B</span><strong>{report.fundamentals_snapshot.pb_ratio}</strong></div>}
                    {report.fundamentals_snapshot.roe && <div className="snap-item"><span>ROE</span><strong>{report.fundamentals_snapshot.roe}%</strong></div>}
                    {report.fundamentals_snapshot.debt_to_equity != null && <div className="snap-item"><span>D/E</span><strong>{report.fundamentals_snapshot.debt_to_equity}</strong></div>}
                    {report.fundamentals_snapshot.revenue_growth && <div className="snap-item"><span>Rev Growth</span><strong>{report.fundamentals_snapshot.revenue_growth}%</strong></div>}
                    {report.fundamentals_snapshot.profit_margin && <div className="snap-item"><span>Net Margin</span><strong>{report.fundamentals_snapshot.profit_margin}%</strong></div>}
                    {report.fundamentals_snapshot.earnings_quality_grade && <div className="snap-item"><span>Earnings Quality</span><strong>{report.fundamentals_snapshot.earnings_quality_grade}</strong></div>}
                    {report.fundamentals_snapshot.governance_grade && <div className="snap-item"><span>Governance</span><strong>{report.fundamentals_snapshot.governance_grade}</strong></div>}
                    {report.fundamentals_snapshot.insider_holding && <div className="snap-item"><span>Promoter</span><strong>{report.fundamentals_snapshot.insider_holding}%</strong></div>}
                    {report.fundamentals_snapshot.dividend_yield && <div className="snap-item"><span>Div Yield</span><strong>{report.fundamentals_snapshot.dividend_yield}%</strong></div>}
                  </div>
                </div>
              )}

              {/* Data Checklist */}
              {report.data_checklist && (
                <div className="data-checklist">
                  <h5>Data Availability</h5>
                  <div className="checklist-grid">
                    {Object.entries(report.data_checklist).map(([key, val]) => (
                      <span key={key} className={`checklist-item ${val ? 'available' : 'missing'}`}>
                        {val ? <CheckCircle size={12} /> : <XCircle size={12} />}
                        {key.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Analysis Tab */}
        {tab === 'analysis' && (
          <div className="tab-content">
            {/* Executive Summary */}
            {report.executive_summary && (
              <div className="executive-summary">
                <h4><FileText size={16} /> Executive Summary</h4>
                <p>{report.executive_summary}</p>
              </div>
            )}

            {/* Long-Term View */}
            {report.long_term_view && (
              <div className="view-section long-term">
                <h5><TrendingUp size={14} /> Long-Term View ({report.long_term_view.horizon})</h5>
                <p className="view-thesis">{report.long_term_view.thesis}</p>
                {report.long_term_view.key_factors?.length > 0 && (
                  <ul className="view-factors">
                    {report.long_term_view.key_factors.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </div>
            )}

            {/* Short-Term View */}
            {report.short_term_view && (
              <div className="view-section short-term">
                <h5><Activity size={14} /> Short-Term View ({report.short_term_view.horizon})</h5>
                <p className="view-thesis">{report.short_term_view.thesis}</p>
                {report.short_term_view.key_factors?.length > 0 && (
                  <ul className="view-factors">
                    {report.short_term_view.key_factors.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </div>
            )}

            {/* Catalysts & Risks */}
            <div className="catalysts-risks-grid">
              {report.key_catalysts?.length > 0 && (
                <div className="catalysts-section">
                  <h5><TrendingUp size={14} /> Key Catalysts</h5>
                  <ul>{report.key_catalysts.map((c, i) => <li key={i}>{c}</li>)}</ul>
                </div>
              )}
              {report.key_risks?.length > 0 && (
                <div className="risks-section">
                  <h5><AlertTriangle size={14} /> Key Risks</h5>
                  <ul>{report.key_risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
            </div>

            {/* Red Flags */}
            {report.classification?.red_flags?.length > 0 && (
              <div className="red-flags-section">
                <h5><XCircle size={14} /> Red Flags</h5>
                <ul>{report.classification.red_flags.map((f, i) => <li key={i}>{f}</li>)}</ul>
              </div>
            )}

            {/* Sector Rotation */}
            {report.sector_rotation?.data_available && (
              <div className="sector-rotation-section">
                <h5>Sector Rotation: {report.sector_rotation.sector}</h5>
                <div className="rotation-stats">
                  <span>Regime: <strong>{report.sector_rotation.regime}</strong></span>
                  {report.sector_rotation.relative_strength_1m != null && <span>RS 1M: <strong>{report.sector_rotation.relative_strength_1m}%</strong></span>}
                  {report.sector_rotation.relative_strength_3m != null && <span>RS 3M: <strong>{report.sector_rotation.relative_strength_3m}%</strong></span>}
                </div>
              </div>
            )}

            {/* Data Quality Notes */}
            {report.data_quality_notes?.length > 0 && (
              <div className="data-quality-notes">
                <h5>Data Quality Notes</h5>
                <ul>{report.data_quality_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </div>
            )}
          </div>
        )}

        {/* Scenarios Tab */}
        {tab === 'scenarios' && report.scenarios && (
          <div className="tab-content">
            <h4><Activity size={16} /> Bull / Base / Bear Scenarios</h4>
            <div className="scenarios-grid">
              {['bull', 'base', 'bear'].map(key => {
                const s = report.scenarios[key];
                if (!s || !s.label) return null;
                const colorMap = { bull: '#22c55e', base: '#eab308', bear: '#ef4444' };
                return (
                  <div key={key} className={`scenario-card ${key}`} style={{ borderTopColor: colorMap[key] }}>
                    <div className="scenario-header">
                      <span className="scenario-label" style={{ color: colorMap[key] }}>{s.label}</span>
                      <span className="scenario-prob">{s.probability}</span>
                    </div>
                    <div className="scenario-targets">
                      <div className="scenario-target">
                        <span>Short-Term</span>
                        <strong>{formatPrice(s.short_term_target)}</strong>
                        <span className="scenario-change" style={{ color: colorMap[key] }}>
                          {s.short_term_target > report.scenarios.current_price ? '+' : ''}
                          {((s.short_term_target / report.scenarios.current_price - 1) * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="scenario-target">
                        <span>3-Year</span>
                        <strong>{formatPrice(s.long_term_target_3y)}</strong>
                        <span className="scenario-change" style={{ color: colorMap[key] }}>
                          {s.long_term_target_3y > report.scenarios.current_price ? '+' : ''}
                          {((s.long_term_target_3y / report.scenarios.current_price - 1) * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                    <p className="scenario-desc">{s.description}</p>
                  </div>
                );
              })}
            </div>

            {/* News Sentiment */}
            {report.news && report.news.count > 0 && (
              <div className="news-sentiment-section">
                <h5>News Sentiment</h5>
                <div className="news-sentiment-stats">
                  <span>Overall: <strong>{report.news.overall_sentiment}</strong></span>
                  <span className="bullish-count">{report.news.bullish_count} bullish</span>
                  <span className="bearish-count">{report.news.bearish_count} bearish</span>
                </div>
                {report.news.items?.slice(0, 3).map((item, i) => (
                  <div key={i} className="news-mini-item">
                    <span className={`news-mini-signal ${item.signal?.toLowerCase()}`}>{item.signal}</span>
                    <span className="news-mini-headline">{item.headline?.substring(0, 100)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="weekly-picks-panel loading">
        <div className="picks-header">
          <h2><Zap size={24} /> Weekly Swing Picks</h2>
        </div>
        <div className="picks-loading">
          <RefreshCw className="spinning" size={32} />
          <p>Analyzing 700+ stocks for best opportunities...</p>
          <p style={{ fontSize: '12px', opacity: 0.7 }}>Generating Chief Analyst reports with fundamentals, technicals, and news...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="weekly-picks-panel error">
        <div className="picks-header">
          <h2><Zap size={24} /> Weekly Swing Picks</h2>
        </div>
        <div className="picks-error">
          <AlertTriangle size={24} />
          <p>{error}</p>
          <button onClick={fetchWeeklyPicks}>Try Again</button>
        </div>
      </div>
    );
  }

  if (!picksData || !picksData.picks || picksData.picks.length === 0) {
    return (
      <div className="weekly-picks-panel empty">
        <div className="picks-header">
          <h2><Zap size={24} /> Weekly Swing Picks</h2>
        </div>
        <div className="no-picks">
          <p>{picksData?.message || 'No qualifying stocks found this week. Market conditions may not be favorable for swing trading.'}</p>
          {picksData?.market_regime && (
            <p className="regime-note">Market Regime: <strong>{picksData.market_regime.regime}</strong> — {picksData.market_regime.reason}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="weekly-picks-panel">
      <div className="picks-header">
        <div className="header-title">
          <h2><Zap size={24} /> Weekly Swing Picks</h2>
          <span className="picks-badge">TOP 2</span>
        </div>
        <button className="refresh-btn" onClick={fetchWeeklyPicks} disabled={loading}>
          <RefreshCw size={18} className={loading ? 'spinning' : ''} />
        </button>
      </div>

      {/* Strategy Summary */}
      <div className="strategy-summary">
        <div className="strategy-header">
          <Calendar size={16} />
          <span>Week: {picksData.strategy.week}</span>
        </div>
        <div className="strategy-details">
          <div className="strategy-stat">
            <span className="stat-label">Strategy</span>
            <span className="stat-value">{picksData.strategy.strategy_name}</span>
          </div>
          <div className="strategy-stat">
            <span className="stat-label">Expected Return</span>
            <span className="stat-value highlight">{picksData.strategy.expected_return}</span>
          </div>
          <div className="strategy-stat">
            <span className="stat-label">Win Rate</span>
            <span className="stat-value">{picksData.strategy.win_rate_historical}</span>
          </div>
          <div className="strategy-stat">
            <span className="stat-label">Analyzed</span>
            <span className="stat-value">{picksData.total_candidates_analyzed} stocks</span>
          </div>
        </div>
      </div>

      {/* Market Regime */}
      {picksData.market_regime && (
        <div className={`market-regime-banner ${picksData.market_regime.regime?.toLowerCase()}`}>
          <Activity size={16} />
          <span>Market: <strong>{picksData.market_regime.regime}</strong></span>
          <span className="regime-reason">{picksData.market_regime.reason}</span>
        </div>
      )}

      {/* Data Freshness Warning */}
      {picksData.data_freshness && (
        <div className={`data-freshness-banner ${picksData.data_freshness.status.toLowerCase()}`}>
          <Clock size={16} />
          <span className="freshness-message">{picksData.data_freshness.message}</span>
          {picksData.data_freshness.status === 'STALE' && (
            <span className="freshness-note">Picks rotate weekly for variety</span>
          )}
        </div>
      )}

      {/* Top Picks */}
      <div className="picks-container">
        {picksData.picks.map((pick, index) => (
          <div key={pick.symbol} className={`pick-card ${expandedPick === pick.symbol ? 'expanded' : ''}`}>
            {/* Pick Header */}
            <div className="pick-header" onClick={() => toggleExpand(pick.symbol)}>
              <div className="pick-rank">
                <Award size={20} />
                <span>#{index + 1}</span>
              </div>
              <div className="pick-info">
                <h3
                  className="pick-symbol"
                  onClick={(e) => { e.stopPropagation(); onStockClick && onStockClick(pick.symbol); }}
                >
                  {pick.symbol}
                </h3>
                <span className="pick-sector">{pick.sector}</span>
              </div>
              <div className="pick-price">
                <span className="price-label">Current</span>
                <span className="price-value">{formatPrice(pick.current_price)}</span>
              </div>
              <div className="pick-score">
                <span className="score-value">{pick.swing_score}</span>
                <span className="score-label">Score</span>
              </div>
              {/* Classification Tag */}
              {pick.analyst_report?.classification?.tag && (
                <span className="classification-mini-tag" style={{
                  background: getTagColor(pick.analyst_report.classification.tag) + '22',
                  color: getTagColor(pick.analyst_report.classification.tag),
                  border: `1px solid ${getTagColor(pick.analyst_report.classification.tag)}44`,
                  padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700
                }}>
                  {pick.analyst_report.classification.tag}
                </span>
              )}
              <span className={`confidence-badge ${getConfidenceBadgeClass(pick.confidence)}`}>
                {pick.confidence}
              </span>
              <button className="expand-btn">
                {expandedPick === pick.symbol ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </button>
            </div>

            {/* Expanded Details */}
            {expandedPick === pick.symbol && (
              <div className="pick-details">
                {/* Why This Stock */}
                <div className="factors-section">
                  <h4><TrendingUp size={16} /> Why This Stock?</h4>
                  <div className="factors-list">
                    {pick.factors.map((factor, idx) => (
                      <span key={idx} className="factor-tag">{factor}</span>
                    ))}
                  </div>
                </div>

                {/* Chief Analyst Report */}
                {renderAnalystReport(pick)}

                {/* Action Button */}
                <button
                  className="view-details-btn"
                  onClick={() => onStockClick && onStockClick(pick.symbol)}
                >
                  View Full Stock Analysis
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Trading Rules */}
      <div className="trading-rules">
        <h4><AlertTriangle size={16} /> Key Trading Rules</h4>
        <ul>
          {picksData.strategy.key_rules.map((rule, idx) => (
            <li key={idx}>{rule}</li>
          ))}
        </ul>
      </div>

      {/* Alternative Candidates */}
      {picksData.alternatives && picksData.alternatives.length > 0 && (
        <div className="alternatives-section">
          <h4><Users size={16} /> Other Strong Candidates</h4>
          <div className="alternatives-list">
            {picksData.alternatives.map((alt) => (
              <div
                key={alt.symbol}
                className="alternative-item"
                onClick={() => onStockClick && onStockClick(alt.symbol)}
              >
                <span className="alt-symbol">{alt.symbol}</span>
                <span className="alt-sector">{alt.sector}</span>
                <span className="alt-score">{alt.score}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <div className="disclaimer">
        <p>{picksData.disclaimer}</p>
        <p className="data-info">Data as of: {picksData.data_date} | Generated: {picksData.generated_at}</p>
      </div>
    </div>
  );
};

export default WeeklySwingPicks;
