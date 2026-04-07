import React, { useState, useEffect, useMemo } from 'react';
import { screenerAPI } from '../services/api';
import { TrendingUp, TrendingDown, ChevronDown, ChevronRight, ChevronUp, RefreshCw, BarChart2, Eye, EyeOff, Award, Zap, ArrowUpDown, Flame } from 'lucide-react';

const PERIODS = ['1d', '2d', '5d', '7d', '1m'];

const SORT_OPTIONS = [
  { value: 'return', label: 'Return %' },
  { value: 'breadth', label: 'Breadth %' },
  { value: 'stocks', label: 'Stock Count' },
  { value: 'consistency', label: 'Consistency' }
];

function SectorPerformanceGrid({ onStockClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSector, setExpandedSector] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('1m');
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(false);
  const [showOnlyGreen, setShowOnlyGreen] = useState(false);
  const [sortBy, setSortBy] = useState('return');
  const [showMomentumLeaders, setShowMomentumLeaders] = useState(true);

  useEffect(() => {
    fetchSectorPerformance();
  }, []);

  const fetchSectorPerformance = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await screenerAPI.getSectorPerformance();
      setData(result);
    } catch (err) {
      setError('Failed to fetch sector performance');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSector = (sectorName) => {
    setExpandedSector(expandedSector === sectorName ? null : sectorName);
  };

  const getReturnColor = (value) => {
    if (value > 5) return '#10b981';
    if (value > 2) return '#22c55e';
    if (value > 0) return '#84cc16';
    if (value > -2) return '#f59e0b';
    if (value > -5) return '#f97316';
    return '#ef4444';
  };

  const getReturnBgColor = (value) => {
    if (value > 0) return 'rgba(34, 197, 94, 0.15)';
    return 'rgba(239, 68, 68, 0.15)';
  };

  // Calculate sector consistency (how many periods are green)
  const getSectorConsistency = (sector) => {
    let greenCount = 0;
    PERIODS.forEach(period => {
      if (sector.periods[period]?.is_positive) greenCount++;
    });
    return greenCount;
  };

  // Find momentum leader stocks (green in all periods)
  const momentumLeaders = useMemo(() => {
    if (!data?.sectors) return [];

    const leaders = [];
    data.sectors.forEach(sector => {
      if (!sector.stocks) return;
      sector.stocks.forEach(stock => {
        // Check if stock has positive return in 1m and 1d
        if (stock.return_1m > 5 && stock.return_1d > 0) {
          leaders.push({
            ...stock,
            sector: sector.sector,
            momentum_score: stock.return_1m + (stock.return_1d * 2) // Weight recent performance
          });
        }
      });
    });

    return leaders.sort((a, b) => b.momentum_score - a.momentum_score).slice(0, 10);
  }, [data]);

  // Sort sectors based on selected criteria
  const sortedSectors = useMemo(() => {
    if (!data?.sectors) return [];

    let sectors = [...data.sectors];

    // Filter first if needed
    if (showOnlyGreen) {
      sectors = sectors.filter(s => s.periods[selectedPeriod]?.is_positive);
    }

    // Then sort
    sectors.sort((a, b) => {
      switch (sortBy) {
        case 'return':
          return (b.periods[selectedPeriod]?.return_pct || 0) - (a.periods[selectedPeriod]?.return_pct || 0);
        case 'breadth':
          return (b.periods[selectedPeriod]?.breadth || 0) - (a.periods[selectedPeriod]?.breadth || 0);
        case 'stocks':
          return b.stock_count - a.stock_count;
        case 'consistency':
          return getSectorConsistency(b) - getSectorConsistency(a);
        default:
          return 0;
      }
    });

    return sectors;
  }, [data, selectedPeriod, showOnlyGreen, sortBy]);

  // Get rank badge for top 3 sectors
  const getRankBadge = (index) => {
    if (index === 0) return <Award size={14} className="rank-badge gold" />;
    if (index === 1) return <Award size={14} className="rank-badge silver" />;
    if (index === 2) return <Award size={14} className="rank-badge bronze" />;
    return null;
  };

  if (loading) {
    return (
      <div className="sector-performance-grid loading-state">
        <RefreshCw className="spin" size={24} />
        <span>Loading sector performance...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sector-performance-grid error-state">
        <span>{error}</span>
        <button onClick={fetchSectorPerformance}>Retry</button>
      </div>
    );
  }

  if (!data || !data.sectors) {
    return null;
  }

  return (
    <div className={`sector-performance-grid ${isPanelCollapsed ? 'collapsed' : ''}`}>
      <div className="sector-perf-header" onClick={() => setIsPanelCollapsed(!isPanelCollapsed)}>
        <h3>
          <BarChart2 size={20} />
          Sector Performance by Period
          {isPanelCollapsed ? <ChevronDown size={18} style={{ marginLeft: '0.5rem' }} /> : <ChevronUp size={18} style={{ marginLeft: '0.5rem' }} />}
        </h3>
        <div className="sector-perf-meta" onClick={(e) => e.stopPropagation()}>
          <span className="date-badge">As of {data.date}</span>
          <span className="green-badge">
            <TrendingUp size={14} /> {data.green_count} Green
          </span>
          <span className="red-badge">
            <TrendingDown size={14} /> {data.red_count} Red
          </span>
          <button
            className={`filter-toggle ${showOnlyGreen ? 'active' : ''}`}
            onClick={() => setShowOnlyGreen(!showOnlyGreen)}
            title={showOnlyGreen ? 'Show all sectors' : 'Show only green sectors'}
          >
            {showOnlyGreen ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
          <button className="refresh-btn" onClick={fetchSectorPerformance}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {!isPanelCollapsed && (
        <>
          {/* Momentum Leaders Section */}
          {showMomentumLeaders && momentumLeaders.length > 0 && (
            <div className="momentum-leaders-section">
              <div className="momentum-header">
                <h4><Flame size={16} /> Momentum Leaders</h4>
                <button
                  className="toggle-btn"
                  onClick={() => setShowMomentumLeaders(false)}
                >
                  Hide
                </button>
              </div>
              <div className="momentum-grid">
                {momentumLeaders.map((stock, idx) => (
                  <div
                    key={stock.symbol}
                    className="momentum-stock"
                    onClick={() => onStockClick && onStockClick(stock.symbol)}
                  >
                    <div className="momentum-rank">#{idx + 1}</div>
                    <div className="momentum-info">
                      <span className="momentum-symbol">{stock.symbol}</span>
                      <span className="momentum-sector">{stock.sector}</span>
                    </div>
                    <div className="momentum-returns">
                      <span className="momentum-1m" style={{ color: getReturnColor(stock.return_1m) }}>
                        1M: {stock.return_1m > 0 ? '+' : ''}{stock.return_1m.toFixed(1)}%
                      </span>
                      <span className="momentum-1d" style={{ color: getReturnColor(stock.return_1d) }}>
                        1D: {stock.return_1d > 0 ? '+' : ''}{stock.return_1d.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!showMomentumLeaders && momentumLeaders.length > 0 && (
            <button
              className="show-momentum-btn"
              onClick={() => setShowMomentumLeaders(true)}
            >
              <Flame size={14} /> Show Momentum Leaders ({momentumLeaders.length})
            </button>
          )}

          {/* Controls Row */}
          <div className="sector-controls-row">
            {/* Period Selector */}
            <div className="period-selector">
              {PERIODS.map(period => (
                <button
                  key={period}
                  className={`period-btn ${selectedPeriod === period ? 'active' : ''}`}
                  onClick={() => setSelectedPeriod(period)}
                >
                  {period.toUpperCase()}
                </button>
              ))}
            </div>

            {/* Sort Selector */}
            <div className="sort-selector">
              <ArrowUpDown size={14} />
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                {SORT_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Sectors Table */}
          <div className="sectors-table-container">
            <div className="sectors-table">
              <div className="sectors-table-header">
                <div className="col-sector">Sector</div>
                <div className="col-stocks">Stocks</div>
                {PERIODS.map(period => (
                  <div key={period} className={`col-period ${selectedPeriod === period ? 'selected' : ''}`}>
                    {period.toUpperCase()}
                  </div>
                ))}
              </div>

              {sortedSectors.map((sector, index) => (
                <div key={sector.sector} className="sector-row-wrapper">
                  <div
                    className={`sector-row ${expandedSector === sector.sector ? 'expanded' : ''}`}
                    onClick={() => toggleSector(sector.sector)}
                  >
                    <div className="col-sector">
                      {expandedSector === sector.sector ? (
                        <ChevronDown size={16} />
                      ) : (
                        <ChevronRight size={16} />
                      )}
                      {getRankBadge(index)}
                      <span className="sector-name">{sector.sector}</span>
                      {getSectorConsistency(sector) >= 4 && (
                        <Zap size={12} className="consistency-badge" title="Consistent performer" />
                      )}
                    </div>
                    <div className="col-stocks">{sector.stock_count}</div>
                    {PERIODS.map(period => {
                      const periodData = sector.periods[period];
                      const returnPct = periodData?.return_pct || 0;
                      return (
                        <div
                          key={period}
                          className={`col-period ${selectedPeriod === period ? 'selected' : ''}`}
                          style={{
                            backgroundColor: getReturnBgColor(returnPct),
                            color: getReturnColor(returnPct)
                          }}
                        >
                          <span className="return-value">
                            {returnPct > 0 ? '+' : ''}{returnPct.toFixed(2)}%
                          </span>
                          <span className="breadth-info">
                            ({periodData?.positive_stocks || 0}/{periodData?.total_stocks || 0})
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Expanded Stocks View */}
                  {expandedSector === sector.sector && sector.stocks && sector.stocks.length > 0 && (
                    <div className="sector-stocks-expanded">
                      <div className="stocks-header">
                        <span>Top Stocks in {sector.sector}</span>
                        <span className="stocks-count">{sector.stocks.length} stocks shown</span>
                      </div>
                      <div className="stocks-grid">
                        {sector.stocks.map((stock, stockIdx) => (
                          <div
                            key={stock.symbol}
                            className={`stock-item ${stock.return_1m > 10 ? 'hot-stock' : ''}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onStockClick && onStockClick(stock.symbol);
                            }}
                          >
                            <div className="stock-rank">#{stockIdx + 1}</div>
                            <div className="stock-info">
                              <div className="stock-symbol">{stock.symbol}</div>
                              <div className="stock-price">Rs. {stock.close.toFixed(2)}</div>
                            </div>
                            <div className="stock-returns">
                              <div
                                className="stock-return"
                                style={{ color: getReturnColor(stock.return_1m) }}
                              >
                                1M: {stock.return_1m > 0 ? '+' : ''}{stock.return_1m.toFixed(2)}%
                              </div>
                              <div
                                className="stock-return-1d"
                                style={{ color: getReturnColor(stock.return_1d) }}
                              >
                                1D: {stock.return_1d > 0 ? '+' : ''}{stock.return_1d.toFixed(2)}%
                              </div>
                            </div>
                            {stock.return_1m > 10 && (
                              <div className="hot-badge"><Flame size={10} /> Hot</div>
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="view-all-stocks">
                        Click on any stock to view detailed analysis
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="sector-summary">
            <div className="summary-section green">
              <h4><TrendingUp size={16} /> Top Performing ({selectedPeriod.toUpperCase()})</h4>
              <div className="summary-list">
                {sortedSectors
                  .filter(s => s.periods[selectedPeriod]?.is_positive)
                  .slice(0, 10)
                  .map((s, idx) => (
                    <span
                      key={s.sector}
                      className={`summary-tag green ${idx < 3 ? 'top-3' : ''}`}
                      onClick={() => toggleSector(s.sector)}
                    >
                      {idx < 3 && <Award size={10} />}
                      {s.sector} ({s.periods[selectedPeriod]?.return_pct.toFixed(1)}%)
                    </span>
                  ))}
              </div>
            </div>
            <div className="summary-section red">
              <h4><TrendingDown size={16} /> Underperforming ({selectedPeriod.toUpperCase()})</h4>
              <div className="summary-list">
                {data.sectors
                  .filter(s => !s.periods[selectedPeriod]?.is_positive)
                  .sort((a, b) => (a.periods[selectedPeriod]?.return_pct || 0) - (b.periods[selectedPeriod]?.return_pct || 0))
                  .slice(0, 10)
                  .map(s => (
                    <span key={s.sector} className="summary-tag red" onClick={() => toggleSector(s.sector)}>
                      {s.sector} ({s.periods[selectedPeriod]?.return_pct.toFixed(1)}%)
                    </span>
                  ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default SectorPerformanceGrid;
