import React, { useState, useEffect, useCallback } from 'react';
import { Newspaper, RefreshCw, TrendingUp, TrendingDown, Clock, AlertCircle, ChevronDown, ChevronUp, Bell, Filter, Zap, Shield, Eye, AlertTriangle } from 'lucide-react';

const API_BASE = '/api';

const NewsPanel = ({ onStockClick }) => {
  const [news, setNews] = useState([]);
  const [signals, setSignals] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState('all'); // 'all', 'buy', 'sell', 'actionable'
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshCountdown, setRefreshCountdown] = useState(600); // 10 minutes in seconds

  const fetchNews = useCallback(async (forceRefresh = false) => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${API_BASE}/news/latest?force_refresh=${forceRefresh}&days=3`);
      if (!response.ok) throw new Error('Failed to fetch news');
      const data = await response.json();

      setNews(data.news || []);
      setSummary(data.summary || {});
      setLastUpdated(data.last_updated);
      setRefreshCountdown(600); // Reset countdown

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSignals = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/news/signals?min_confidence=50`);
      if (!response.ok) throw new Error('Failed to fetch signals');
      const data = await response.json();
      setSignals(data);
    } catch (err) {
      console.error('Error fetching signals:', err);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchNews();
    fetchSignals();
  }, [fetchNews, fetchSignals]);

  // Auto-refresh every 10 minutes
  useEffect(() => {
    if (!autoRefresh) return;

    const countdownInterval = setInterval(() => {
      setRefreshCountdown(prev => {
        if (prev <= 1) {
          fetchNews(true);
          fetchSignals();
          return 600;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(countdownInterval);
  }, [autoRefresh, fetchNews, fetchSignals]);

  const handleManualRefresh = async () => {
    await fetchNews(true);
    await fetchSignals();
  };

  const formatCountdown = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      const date = new Date(timestamp);
      return date.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return timestamp;
    }
  };

  const getSignalColor = (signal) => {
    switch (signal) {
      case 'STRONG_BUY': return '#22c55e';
      case 'BUY': return '#4ade80';
      case 'SELL': return '#f87171';
      case 'STRONG_SELL': return '#ef4444';
      case 'WATCH': return '#fbbf24';
      default: return '#94a3b8';
    }
  };

  const getSignalBg = (signal) => {
    switch (signal) {
      case 'STRONG_BUY': return 'rgba(34, 197, 94, 0.15)';
      case 'BUY': return 'rgba(74, 222, 128, 0.1)';
      case 'SELL': return 'rgba(248, 113, 113, 0.1)';
      case 'STRONG_SELL': return 'rgba(239, 68, 68, 0.15)';
      case 'WATCH': return 'rgba(251, 191, 36, 0.1)';
      default: return 'rgba(148, 163, 184, 0.1)';
    }
  };

  const filteredNews = news.filter(item => {
    if (filter === 'all') return true;
    if (filter === 'buy') return ['STRONG_BUY', 'BUY'].includes(item.signal);
    if (filter === 'sell') return ['STRONG_SELL', 'SELL'].includes(item.signal);
    if (filter === 'actionable') return item.confidence >= 60 && item.signal !== 'NEUTRAL';
    return true;
  });

  return (
    <div className="news-panel">
      <div className="news-header" onClick={() => setExpanded(!expanded)}>
        <h3>
          <Newspaper size={20} />
          NSE News & Announcements
          {summary && summary.total_news > 0 && (
            <span className="news-badge">{summary.total_news}</span>
          )}
        </h3>
        <div className="news-header-right">
          {autoRefresh && (
            <span className="refresh-countdown">
              <Clock size={14} />
              Next refresh: {formatCountdown(refreshCountdown)}
            </span>
          )}
          <button
            className={`auto-refresh-btn ${autoRefresh ? 'active' : ''}`}
            onClick={(e) => { e.stopPropagation(); setAutoRefresh(!autoRefresh); }}
            title={autoRefresh ? 'Disable auto-refresh' : 'Enable auto-refresh'}
          >
            <Bell size={14} />
          </button>
          <button
            className="refresh-btn"
            onClick={(e) => { e.stopPropagation(); handleManualRefresh(); }}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          </button>
          {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </div>
      </div>

      {expanded && (
        <div className="news-content">
          {/* Summary Stats */}
          {summary && (
            <div className="news-summary">
              <div className="summary-stat">
                <span className="stat-value">{summary.total_news || 0}</span>
                <span className="stat-label">Total News</span>
              </div>
              <div className="summary-stat bullish">
                <TrendingUp size={16} />
                <span className="stat-value">{summary.buy_signals || 0}</span>
                <span className="stat-label">Buy Signals</span>
              </div>
              <div className="summary-stat bearish">
                <TrendingDown size={16} />
                <span className="stat-value">{summary.sell_signals || 0}</span>
                <span className="stat-label">Sell Signals</span>
              </div>
              <div className="summary-stat">
                <span className="stat-value">{summary.symbols_with_signals || 0}</span>
                <span className="stat-label">Stocks Affected</span>
              </div>
            </div>
          )}

          {/* SEBI Analyst View */}
          {summary && summary.sebi_analyst_view && (
            <div className="sebi-analyst-view">
              <h4 className="sebi-header">
                <Shield size={16} />
                SEBI Analyst View
              </h4>
              <div className="sebi-stats">
                <div className="sebi-stat high-priority">
                  <AlertTriangle size={14} />
                  <span className="stat-value">{summary.sebi_analyst_view.high_priority_count || 0}</span>
                  <span className="stat-label">High Priority</span>
                </div>
                <div className="sebi-stat monitoring">
                  <Eye size={14} />
                  <span className="stat-value">{summary.sebi_analyst_view.monitoring_required_count || 0}</span>
                  <span className="stat-label">Monitoring Required</span>
                </div>
                <div className="sebi-stat psi">
                  <Zap size={14} />
                  <span className="stat-value">{summary.sebi_analyst_view.psi_announcements_count || 0}</span>
                  <span className="stat-label">Price Sensitive</span>
                </div>
              </div>
              
              {/* SEBI Category Breakdown */}
              {summary.sebi_analyst_view.category_breakdown && 
               Object.keys(summary.sebi_analyst_view.category_breakdown).length > 0 && (
                <div className="sebi-categories">
                  <span className="categories-label">LODR Categories:</span>
                  <div className="category-tags">
                    {Object.entries(summary.sebi_analyst_view.category_breakdown).map(([cat, count]) => (
                      <span key={cat} className="category-tag">
                        {cat}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {/* High Priority Items */}
              {summary.sebi_analyst_view.high_priority_items?.length > 0 && (
                <div className="high-priority-alerts">
                  <span className="alerts-label">⚠️ Priority Alerts:</span>
                  {summary.sebi_analyst_view.high_priority_items.slice(0, 5).map((item, idx) => (
                    <div 
                      key={idx} 
                      className="priority-item"
                      onClick={() => onStockClick && onStockClick(item.symbol)}
                    >
                      <span className="priority-symbol">{item.symbol}</span>
                      <span className="priority-headline">{item.headline?.substring(0, 80)}...</span>
                      {item.sebi_category?.category_type && (
                        <span className="priority-category">{item.sebi_category.category_type}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Actionable Signals Alert */}
          {signals && (signals.buy_signals?.length > 0 || signals.sell_signals?.length > 0) && (
            <div className="actionable-signals">
              <h4>
                <Zap size={16} />
                Actionable Trading Signals
              </h4>
              <div className="signals-grid">
                {signals.buy_signals?.slice(0, 3).map((signal, idx) => (
                  <div
                    key={`buy-${idx}`}
                    className="signal-card buy"
                    onClick={() => onStockClick && onStockClick(signal.symbol)}
                  >
                    <div className="signal-symbol">{signal.symbol}</div>
                    <div className="signal-type">{signal.signal}</div>
                    <div className="signal-confidence">{signal.confidence}% confidence</div>
                    <div className="signal-reasons">
                      {signal.reasons?.slice(0, 2).join(', ')}
                    </div>
                  </div>
                ))}
                {signals.sell_signals?.slice(0, 3).map((signal, idx) => (
                  <div
                    key={`sell-${idx}`}
                    className="signal-card sell"
                    onClick={() => onStockClick && onStockClick(signal.symbol)}
                  >
                    <div className="signal-symbol">{signal.symbol}</div>
                    <div className="signal-type">{signal.signal}</div>
                    <div className="signal-confidence">{signal.confidence}% confidence</div>
                    <div className="signal-reasons">
                      {signal.reasons?.slice(0, 2).join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filter Tabs */}
          <div className="news-filters">
            <button
              className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All ({news.length})
            </button>
            <button
              className={`filter-tab buy ${filter === 'buy' ? 'active' : ''}`}
              onClick={() => setFilter('buy')}
            >
              <TrendingUp size={14} />
              Buy ({news.filter(n => ['STRONG_BUY', 'BUY'].includes(n.signal)).length})
            </button>
            <button
              className={`filter-tab sell ${filter === 'sell' ? 'active' : ''}`}
              onClick={() => setFilter('sell')}
            >
              <TrendingDown size={14} />
              Sell ({news.filter(n => ['STRONG_SELL', 'SELL'].includes(n.signal)).length})
            </button>
            <button
              className={`filter-tab actionable ${filter === 'actionable' ? 'active' : ''}`}
              onClick={() => setFilter('actionable')}
            >
              <Filter size={14} />
              High Confidence
            </button>
          </div>

          {/* News List */}
          {loading && <div className="news-loading">Loading news...</div>}

          {error && (
            <div className="news-error">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          {!loading && !error && filteredNews.length === 0 && (
            <div className="news-empty">
              No news matching current filter. Try changing the filter or refreshing.
            </div>
          )}

          {!loading && !error && filteredNews.length > 0 && (
            <div className="news-list">
              {filteredNews.slice(0, 50).map((item, idx) => (
                <div
                  key={idx}
                  className={`news-item ${item.priority === 'HIGH' ? 'high-priority' : ''} ${item.monitoring_required ? 'monitoring' : ''}`}
                  style={{ backgroundColor: getSignalBg(item.signal) }}
                  onClick={() => onStockClick && onStockClick(item.symbol)}
                >
                  <div className="news-item-header">
                    <span
                      className="news-symbol"
                      onClick={(e) => { e.stopPropagation(); onStockClick && onStockClick(item.symbol); }}
                    >
                      {item.symbol}
                    </span>
                    <span
                      className="news-signal"
                      style={{ color: getSignalColor(item.signal) }}
                    >
                      {item.signal === 'STRONG_BUY' && <TrendingUp size={14} />}
                      {item.signal === 'BUY' && <TrendingUp size={14} />}
                      {item.signal === 'STRONG_SELL' && <TrendingDown size={14} />}
                      {item.signal === 'SELL' && <TrendingDown size={14} />}
                      {item.signal}
                    </span>
                    <span className="news-confidence">
                      {item.confidence > 0 ? `${item.confidence}%` : ''}
                    </span>
                    {item.priority === 'HIGH' && (
                      <span className="priority-badge">HIGH PRIORITY</span>
                    )}
                    {item.sebi_category?.psi && (
                      <span className="psi-badge" title="Price Sensitive Information">PSI</span>
                    )}
                  </div>
                  <div className="news-headline">{item.headline}</div>
                  
                  {/* SEBI Category Info */}
                  {item.sebi_category && (
                    <div className="sebi-info">
                      <span className="sebi-regulation">{item.sebi_category.name}</span>
                      {item.sebi_category.category_type && item.sebi_category.category_type !== 'General' && (
                        <span className="sebi-type">{item.sebi_category.category_type}</span>
                      )}
                      <span className={`materiality-badge ${item.sebi_category.materiality?.toLowerCase()}`}>
                        {item.sebi_category.materiality}
                      </span>
                    </div>
                  )}
                  
                  {/* Analyst Action */}
                  {item.analyst_action && item.analyst_action !== 'REVIEW' && (
                    <div className="analyst-action">{item.analyst_action}</div>
                  )}
                  
                  {/* Key Points */}
                  {item.key_points && item.key_points.length > 0 && (
                    <div className="key-points">
                      {item.key_points.map((point, i) => (
                        <span key={i} className="key-point">{point}</span>
                      ))}
                    </div>
                  )}
                  
                  <div className="news-item-footer">
                    <span className="news-category">{item.category || item.type}</span>
                    <span className="news-source">{item.source}</span>
                    <span className="news-time">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  {item.reasons && item.reasons.length > 0 && (
                    <div className="news-reasons">
                      {item.reasons.map((reason, i) => (
                        <span key={i} className="reason-tag">{reason}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Last Updated */}
          {lastUpdated && (
            <div className="news-footer">
              Last updated: {formatTimestamp(lastUpdated)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NewsPanel;
