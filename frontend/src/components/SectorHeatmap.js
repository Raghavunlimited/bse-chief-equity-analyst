import React, { useState, useEffect, useMemo } from 'react';
import { screenerAPI } from '../services/api';
import { Calendar, TrendingUp, TrendingDown, RefreshCw, BarChart2 } from 'lucide-react';

function SectorHeatmap() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState({
    startDate: '',
    endDate: ''
  });
  const [presetRange, setPresetRange] = useState('1M');

  useEffect(() => {
    fetchHeatmapData();
  }, []);

  const fetchHeatmapData = async (start = null, end = null) => {
    try {
      setLoading(true);
      setError(null);
      const response = await screenerAPI.getSectorHeatmap(start, end);
      setData(response);
      // Update date inputs with actual dates used
      if (response.start_date) setDateRange(prev => ({ ...prev, startDate: response.start_date }));
      if (response.end_date) setDateRange(prev => ({ ...prev, endDate: response.end_date }));
    } catch (err) {
      console.error('Failed to fetch heatmap:', err);
      setError('Failed to load sector heatmap');
    } finally {
      setLoading(false);
    }
  };

  const handlePresetChange = (preset) => {
    setPresetRange(preset);
    const endDate = new Date();
    let startDate = new Date();

    switch (preset) {
      case '1W':
        startDate.setDate(endDate.getDate() - 7);
        break;
      case '2W':
        startDate.setDate(endDate.getDate() - 14);
        break;
      case '1M':
        startDate.setMonth(endDate.getMonth() - 1);
        break;
      case '3M':
        startDate.setMonth(endDate.getMonth() - 3);
        break;
      case 'ALL':
        startDate = null;
        break;
      default:
        startDate.setMonth(endDate.getMonth() - 1);
    }

    const startStr = startDate ? startDate.toISOString().split('T')[0] : null;
    const endStr = endDate.toISOString().split('T')[0];

    fetchHeatmapData(startStr, endStr);
  };

  const handleCustomDateChange = () => {
    if (dateRange.startDate && dateRange.endDate) {
      setPresetRange('custom');
      fetchHeatmapData(dateRange.startDate, dateRange.endDate);
    }
  };

  // Get color based on change percentage
  const getHeatColor = (changePct) => {
    if (changePct === null || changePct === undefined) return '#1a1f3a';

    if (changePct >= 3) return '#15803d';      // Strong green
    if (changePct >= 2) return '#22c55e';      // Green
    if (changePct >= 1) return '#4ade80';      // Light green
    if (changePct >= 0.5) return '#86efac';    // Very light green
    if (changePct >= 0) return '#bbf7d0';      // Pale green
    if (changePct >= -0.5) return '#fecaca';   // Pale red
    if (changePct >= -1) return '#fca5a5';     // Very light red
    if (changePct >= -2) return '#f87171';     // Light red
    if (changePct >= -3) return '#ef4444';     // Red
    return '#dc2626';                           // Strong red
  };

  const getTextColor = (changePct) => {
    if (changePct === null || changePct === undefined) return '#6b7280';
    if (Math.abs(changePct) <= 0.5) return '#1f2937';
    return '#ffffff';
  };

  // Format date for display
  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  };

  // Memoize recent dates to show (last 20 trading days)
  const recentHeatmapData = useMemo(() => {
    if (!data?.heatmap_data) return [];
    return data.heatmap_data.slice(-20);
  }, [data]);

  if (loading) {
    return (
      <div className="sector-heatmap loading">
        <RefreshCw className="spin" size={24} />
        <span>Loading heatmap data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sector-heatmap error">
        <span>{error}</span>
        <button onClick={() => fetchHeatmapData()}>Retry</button>
      </div>
    );
  }

  if (!data || !data.sectors || data.sectors.length === 0) {
    return (
      <div className="sector-heatmap empty">
        <span>No sector data available</span>
      </div>
    );
  }

  return (
    <div className="sector-heatmap">
      <div className="heatmap-header">
        <h2><BarChart2 size={24} /> Sector Performance Heatmap</h2>
        <div className="heatmap-controls">
          <div className="preset-buttons">
            {['1W', '2W', '1M', '3M', 'ALL'].map(preset => (
              <button
                key={preset}
                className={`preset-btn ${presetRange === preset ? 'active' : ''}`}
                onClick={() => handlePresetChange(preset)}
              >
                {preset}
              </button>
            ))}
          </div>
          <div className="date-inputs">
            <input
              type="date"
              value={dateRange.startDate}
              onChange={(e) => setDateRange(prev => ({ ...prev, startDate: e.target.value }))}
            />
            <span>to</span>
            <input
              type="date"
              value={dateRange.endDate}
              onChange={(e) => setDateRange(prev => ({ ...prev, endDate: e.target.value }))}
            />
            <button className="apply-btn" onClick={handleCustomDateChange}>
              <Calendar size={16} /> Apply
            </button>
          </div>
        </div>
      </div>

      {/* Period Summary */}
      <div className="period-summary">
        <h3>Period Performance ({data.start_date} to {data.end_date})</h3>
        <div className="summary-grid">
          {data.sector_summary?.slice(0, 12).map((sector, idx) => (
            <div
              key={sector.sector}
              className={`summary-card ${sector.period_return >= 0 ? 'positive' : 'negative'}`}
            >
              <div className="summary-rank">#{idx + 1}</div>
              <div className="summary-content">
                <div className="summary-sector">{sector.sector}</div>
                <div className="summary-return">
                  {sector.period_return >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  <span className={sector.period_return >= 0 ? 'green' : 'red'}>
                    {sector.period_return >= 0 ? '+' : ''}{sector.period_return}%
                  </span>
                </div>
                <div className="summary-details">
                  <span>Win Rate: {sector.win_rate}%</span>
                  <span>{sector.stock_count} stocks</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Heatmap Grid */}
      <div className="heatmap-container">
        <h3>Daily Sector Performance (Last {recentHeatmapData.length} Days)</h3>
        <div className="heatmap-scroll">
          <table className="heatmap-table">
            <thead>
              <tr>
                <th className="sector-header">Sector</th>
                {recentHeatmapData.map(day => (
                  <th key={day.date} className="date-header">
                    {formatDate(day.date)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.sectors.map(sector => (
                <tr key={sector}>
                  <td className="sector-name">{sector}</td>
                  {recentHeatmapData.map(day => {
                    const sectorData = day.sectors[sector];
                    const changePct = sectorData?.change_pct;
                    return (
                      <td
                        key={day.date}
                        className="heat-cell"
                        style={{
                          backgroundColor: getHeatColor(changePct),
                          color: getTextColor(changePct)
                        }}
                        title={`${sector} on ${day.date}: ${changePct !== null ? changePct.toFixed(2) + '%' : 'N/A'}`}
                      >
                        {changePct !== null ? (
                          <span>{changePct > 0 ? '+' : ''}{changePct.toFixed(1)}</span>
                        ) : (
                          <span>-</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Legend */}
        <div className="heatmap-legend">
          <span className="legend-label">Strong Sell</span>
          <div className="legend-gradient">
            <div style={{ backgroundColor: '#dc2626' }}></div>
            <div style={{ backgroundColor: '#ef4444' }}></div>
            <div style={{ backgroundColor: '#f87171' }}></div>
            <div style={{ backgroundColor: '#fca5a5' }}></div>
            <div style={{ backgroundColor: '#fecaca' }}></div>
            <div style={{ backgroundColor: '#e5e7eb' }}></div>
            <div style={{ backgroundColor: '#bbf7d0' }}></div>
            <div style={{ backgroundColor: '#86efac' }}></div>
            <div style={{ backgroundColor: '#4ade80' }}></div>
            <div style={{ backgroundColor: '#22c55e' }}></div>
            <div style={{ backgroundColor: '#15803d' }}></div>
          </div>
          <span className="legend-label">Strong Buy</span>
        </div>
      </div>
    </div>
  );
}

export default SectorHeatmap;
