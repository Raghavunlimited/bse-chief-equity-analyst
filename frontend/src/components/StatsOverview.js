import React from 'react';
import { Database, Calendar, TrendingUp, AlertTriangle, Clock } from 'lucide-react';

function StatsOverview({ stats }) {
  const { total_symbols, date_range, latest_candidates } = stats;
  
  // Calculate data freshness
  const getDataFreshness = () => {
    if (!date_range?.max) return { days: null, status: 'unknown' };
    const today = new Date();
    const latestDate = new Date(date_range.max);
    const diffTime = today - latestDate;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays <= 1) return { days: diffDays, status: 'fresh', label: 'Current' };
    if (diffDays <= 3) return { days: diffDays, status: 'recent', label: `${diffDays} days old` };
    if (diffDays <= 7) return { days: diffDays, status: 'stale', label: `${diffDays} days old` };
    return { days: diffDays, status: 'outdated', label: `${diffDays} days old` };
  };
  
  const freshness = getDataFreshness();

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <h3>
          <Database size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
          Total Stocks
        </h3>
        <div className="value">{total_symbols?.toLocaleString() || 0}</div>
      </div>

      <div className="stat-card">
        <h3>
          <Calendar size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
          Data Range
        </h3>
        <div className="value" style={{ fontSize: '1.2rem' }}>
          {date_range?.min && date_range?.max ? (
            <>
              {new Date(date_range.min).toLocaleDateString()} - {new Date(date_range.max).toLocaleDateString()}
            </>
          ) : (
            'No data'
          )}
        </div>
      </div>
      
      <div className={`stat-card ${freshness.status === 'outdated' ? 'stat-card-warning' : freshness.status === 'stale' ? 'stat-card-caution' : ''}`}>
        <h3>
          {freshness.status === 'outdated' || freshness.status === 'stale' ? (
            <AlertTriangle size={16} style={{ display: 'inline', marginRight: '0.5rem', color: freshness.status === 'outdated' ? '#f97316' : '#eab308' }} />
          ) : (
            <Clock size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
          )}
          Data Freshness
        </h3>
        <div className="value" style={{ 
          fontSize: '1rem', 
          color: freshness.status === 'outdated' ? '#f97316' : freshness.status === 'stale' ? '#eab308' : freshness.status === 'fresh' ? '#22c55e' : '#94a3b8'
        }}>
          {freshness.label || 'Unknown'}
        </div>
        {freshness.status === 'outdated' && (
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.25rem' }}>
            Same picks expected until data updates
          </div>
        )}
      </div>

      <div className="stat-card">
        <h3>
          <TrendingUp size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
          Latest Candidates
        </h3>
        <div className="value">{latest_candidates || 0}</div>
      </div>
    </div>
  );
}

export default StatsOverview;
