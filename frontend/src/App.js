import React, { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import './App.css';
import { screenerAPI } from './services/api';
import CandidateCard from './components/CandidateCard';
import StatsOverview from './components/StatsOverview';
import StockDetailModal from './components/StockDetailModal';
import WeeklySwingPicks from './components/WeeklySwingPicks';
import { RefreshCw, TrendingUp, Database, Activity, HelpCircle, Zap, Filter, AlertTriangle, Target, Download, X, Search } from 'lucide-react';

// Lazy load less critical components
const BacktestPanel = lazy(() => import('./components/BacktestPanel'));
const DateSelector = lazy(() => import('./components/DateSelector'));
const ScoreExplanation = lazy(() => import('./components/ScoreExplanation'));
const MarketRegimePanel = lazy(() => import('./components/MarketRegimePanel'));
const SectorAnalysisPanel = lazy(() => import('./components/SectorAnalysisPanel'));
const SectorHeatmap = lazy(() => import('./components/SectorHeatmap'));
const SectorPerformanceGrid = lazy(() => import('./components/SectorPerformanceGrid'));
const SeasonalityHeatmap = lazy(() => import('./components/SeasonalityHeatmap'));
const MonthlySectorPicks = lazy(() => import('./components/MonthlySectorPicks'));
const NewsPanel = lazy(() => import('./components/NewsPanel'));
const SectorValuationPanel = lazy(() => import('./components/SectorValuationPanel'));
const StockSearchModal = lazy(() => import('./components/StockSearchModal'));
const MultibaggerPicks = lazy(() => import('./components/MultibaggerPicks'));
const FuturisticSectors = lazy(() => import('./components/FuturisticSectors'));

// Loading fallback component
const LoadingFallback = () => (
  <div className="lazy-loading-enhanced">
    <div className="lazy-loading-spinner">
      <RefreshCw className="spinning" size={24} />
    </div>
    <span>Loading component...</span>
  </div>
);

function App() {
  const [candidates, setCandidates] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedStock, setSelectedStock] = useState(null);
  const [showScoreExplanation, setShowScoreExplanation] = useState(false);
  // eslint-disable-next-line no-unused-vars
  const [marketRegime, setMarketRegime] = useState(null);  // Reserved for future market regime-based filtering
  const [enhancedMode, setEnhancedMode] = useState('elite'); // 'basic', 'enhanced', 'ultimate', 'elite'
  const [filterStats, setFilterStats] = useState(null);
  const [autoRefreshStatus, setAutoRefreshStatus] = useState('');
  
  // Bulk download state
  const [showBulkDownloadModal, setShowBulkDownloadModal] = useState(false);
  const [bulkDownloadStatus, setBulkDownloadStatus] = useState(null);
  const [isPollingStatus, setIsPollingStatus] = useState(false);
  const [downloadStarting, setDownloadStarting] = useState(null); // tracks which button was clicked (1, 5, or 10)
  
  // Stock search modal state
  const [showStockSearchModal, setShowStockSearchModal] = useState(false);

  // Auto-fetch fresh data and run screener on mount
  useEffect(() => {
    autoFetchAndScreen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch results when date changes
  useEffect(() => {
    if (selectedDate) {
      fetchResultsByDate(selectedDate);
    }
  }, [selectedDate]);

  // Auto-fetch latest data and run screener - memoized
  const autoFetchAndScreen = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setAutoRefreshStatus('Fetching latest market data...');

      // Try to ingest latest data
      const ingestResult = await screenerAPI.ingestLatest();

      if (ingestResult.status === 'success') {
        setAutoRefreshStatus(`Data loaded for ${ingestResult.date}. Running screener...`);

        // Wait a moment for indicators to compute
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Run the appropriate screener based on mode
        await runScreenerByMode();
      } else {
        // If ingest fails (e.g., holiday), just run screener on existing data
        setAutoRefreshStatus('Using existing data. Running screener...');
        await runScreenerByMode();
      }

      fetchStats();
      setAutoRefreshStatus('');
    } catch (err) {
      console.error('Auto-fetch error:', err);
      // Fallback to existing data
      setAutoRefreshStatus('Using cached data...');
      await runScreenerByMode();
      setAutoRefreshStatus('');
    }
  }, []);

  // Run screener based on current mode
  const runScreenerByMode = async () => {
    try {
      let result;
      if (enhancedMode === 'elite') {
        result = await screenerAPI.runEliteScreener({
          top_n: 2,
          capital_per_trade: 100000,
          min_score: 70,
          min_price: 100
        });
      } else if (enhancedMode === 'ultimate') {
        result = await screenerAPI.runUltimateScreener({
          top_n: 20,
          min_score: 50,
          require_pattern: true,
          require_trend: true,
          sector_filter: true,
          max_risk_pct: 5.0
        });
      } else if (enhancedMode === 'enhanced') {
        result = await screenerAPI.runEnhancedScreener({
          top_n: 10,
          min_score: 12,
          apply_market_filter: true,
          apply_sector_filter: true,
          apply_sr_filter: true,
          apply_mtf_filter: true,
          apply_fundamental_filter: true,
          top_sectors: 3
        });
      } else {
        result = await screenerAPI.runScreener();
      }

      if (result.status === 'success') {
        setCandidates(result.candidates || result.results || []);
        setFilterStats(result);
        const count = result.candidates?.length || result.results?.length || 0;
        setSuccess(`Found ${count} investment candidates for today!`);
      }
    } catch (err) {
      // If screener fails, try to get cached results
      console.error('Screener error:', err);
      const data = await screenerAPI.getLatestResults();
      setCandidates(data);
    } finally {
      setLoading(false);
    }
  };

  const fetchResultsByDate = async (date) => {
    try {
      setLoading(true);
      setError(null);
      const data = await screenerAPI.getResultsByDate(date);
      setCandidates(data.results || []);
    } catch (err) {
      setError('Failed to fetch results for selected date.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const data = await screenerAPI.getStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  };

  const handleRunScreener = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);

      const result = await screenerAPI.runScreener();

      if (result.status === 'success') {
        setCandidates(result.results);
        setSuccess(`Screener complete! Found ${result.results.length} candidates for ${result.screening_date}.`);
        setSelectedDate(null);
      }

      fetchStats();
    } catch (err) {
      setError('Failed to run screener: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEnhancedScreener = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      setFilterStats(null);

      const result = await screenerAPI.runEnhancedScreener({
        top_n: 10,
        min_score: 12,
        apply_market_filter: true,
        apply_sector_filter: true,
        apply_sr_filter: true,
        apply_mtf_filter: true,
        apply_fundamental_filter: true,
        top_sectors: 3
      });

      if (result.status === 'success') {
        setCandidates(result.candidates || []);

        // Build success message
        let message = `Enhanced Screener complete! Found ${result.candidates?.length || 0} high-quality candidates.`;
        if (result.filters_applied) {
          message += ` Filters applied: ${result.filters_applied.length}`;
        }
        if (result.rejected_count) {
          message += ` (${result.rejected_count} rejected by filters)`;
        }

        setSuccess(message);
        setFilterStats(result);
        setSelectedDate(null);

        // Check market regime warning
        if (result.market_regime && !result.market_regime.allow_trading) {
          setError(`Warning: ${result.market_regime.reason}. Consider staying in cash.`);
        }
      }

      fetchStats();
    } catch (err) {
      setError('Failed to run enhanced screener: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunUltimateScreener = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      setFilterStats(null);

      const result = await screenerAPI.runUltimateScreener({
        top_n: 20,
        min_score: 50,
        require_pattern: true,
        require_trend: true,
        sector_filter: true,
        max_risk_pct: 5.0
      });

      if (result.status === 'success') {
        setCandidates(result.candidates || []);

        let message = `Ultimate Screener complete! Found ${result.candidates?.length || 0} pattern-confirmed candidates.`;
        if (result.filters_applied) {
          message += ` (${result.filters_applied.length} filters applied)`;
        }

        setSuccess(message);
        setFilterStats(result);
        setSelectedDate(null);
      }

      fetchStats();
    } catch (err) {
      setError('Failed to run ultimate screener: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEliteScreener = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      setFilterStats(null);

      const result = await screenerAPI.runEliteScreener({
        top_n: 2,
        capital_per_trade: 100000,
        min_score: 70,
        min_price: 100
      });

      if (result.status === 'success') {
        setCandidates(result.candidates || []);

        const winRate = result.methodology?.backtest_results?.win_rate || '68%';
        const projectedAnnual = result.methodology?.backtest_results?.projected_annual || '25%';
        let message = `🎯 Elite Screener: Found ${result.candidates?.length || 0} momentum breakout picks! `;
        message += `(${winRate} win rate, ${projectedAnnual} projected annual return)`;

        setSuccess(message);
        setFilterStats(result);
        setSelectedDate(null);
      }

      fetchStats();
    } catch (err) {
      setError('Failed to run elite screener: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleIngestLatest = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);

      const result = await screenerAPI.ingestLatest();

      if (result.status === 'success') {
        setSuccess(`Successfully ingested ${result.records_processed} records for ${result.date}`);
        fetchStats();

        // Auto-run screener after ingestion based on mode
        setTimeout(() => {
          if (enhancedMode === 'ultimate') {
            handleRunUltimateScreener();
          } else if (enhancedMode === 'enhanced') {
            handleRunEnhancedScreener();
          } else {
            handleRunScreener();
          }
        }, 2000);
      } else if (result.status === 'up_to_date') {
        // Data is current - show as info, not error
        setSuccess(result.message);
        fetchStats();
        // Still run screener on existing data
        setTimeout(() => {
          if (enhancedMode === 'elite') {
            handleRunEliteScreener();
          } else if (enhancedMode === 'ultimate') {
            handleRunUltimateScreener();
          } else if (enhancedMode === 'enhanced') {
            handleRunEnhancedScreener();
          } else {
            handleRunScreener();
          }
        }, 500);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError('Failed to ingest data: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleStockClick = (symbol) => {
    setSelectedStock(symbol);
  };

  const handleRegimeChange = (regime) => {
    setMarketRegime(regime);
  };

  // Start bulk historical data download (10 years)
  const handleStartBulkDownload = async (years = 10) => {
    try {
      setDownloadStarting(years);
      setShowBulkDownloadModal(false); // Close modal immediately
      
      const result = await screenerAPI.startBulkDownload(years);
      setBulkDownloadStatus(result);
      
      if (result.status === 'started' || result.status === 'already_running') {
        setIsPollingStatus(true);
        setSuccess(`Started downloading ${years} year${years > 1 ? 's' : ''} of data...`);
        pollDownloadStatus();
      }
      setDownloadStarting(null);
    } catch (err) {
      console.error('Failed to start bulk download:', err);
      setBulkDownloadStatus({ error: err.message });
      setError('Failed to start download: ' + err.message);
      setDownloadStarting(null);
    }
  };

  // Poll for download status
  const pollDownloadStatus = async () => {
    try {
      const status = await screenerAPI.getBulkDownloadStatus();
      setBulkDownloadStatus(status);
      
      if (status.running) {
        // Continue polling every 3 seconds
        setTimeout(pollDownloadStatus, 3000);
      } else {
        setIsPollingStatus(false);
        
        // If completed, refresh data
        if (status.completed) {
          setSuccess(`✅ Downloaded ${status.days_downloaded} trading days! Refreshing screener...`);
          setTimeout(() => {
            autoFetchAndScreen();
          }, 1500);
        } else if (status.error) {
          setError('Download error: ' + status.error);
        }
      }
    } catch (err) {
      console.error('Failed to get download status:', err);
      setIsPollingStatus(false);
    }
  };

  // Check if download is already running on mount
  useEffect(() => {
    const checkExistingDownload = async () => {
      try {
        const status = await screenerAPI.getBulkDownloadStatus();
        if (status.running) {
          setBulkDownloadStatus(status);
          setIsPollingStatus(true);
          pollDownloadStatus();
          // Don't show modal - just show progress in header button
        }
      } catch (err) {
        // Ignore errors
      }
    };
    checkExistingDownload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="header-text">
            <h1>NSE Weekly Swing Trader</h1>
            <p>Advanced momentum-based swing trading screener with win-rate optimization filters</p>
          </div>
          <div className="header-actions">
            <button 
              className="search-stock-btn"
              onClick={() => setShowStockSearchModal(true)}
              title="Search Stock"
            >
              <Search size={18} />
              <span>Search Stock</span>
            </button>
            <button 
              className={`refresh-data-btn ${isPollingStatus ? 'downloading' : ''}`}
              onClick={() => {
                // Reset state if not currently downloading
                if (!isPollingStatus) {
                  setBulkDownloadStatus(null);
                }
                setShowBulkDownloadModal(true);
              }}
              title={isPollingStatus ? `Downloading: ${bulkDownloadStatus?.current_date || 'Starting...'}` : "Update Historical Data"}
            >
              {isPollingStatus ? (
                <>
                  <RefreshCw size={18} className="spinning" />
                  <span>Updating {bulkDownloadStatus?.progress || 0}%</span>
                </>
              ) : (
                <>
                  <Download size={18} />
                  <span>Update Data</span>
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Bulk Download Modal */}
      {showBulkDownloadModal && (
        <div className="modal-overlay" onClick={() => setShowBulkDownloadModal(false)}>
          <div className="bulk-download-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3><Database size={20} /> Update Historical Data</h3>
              <button className="close-btn" onClick={() => setShowBulkDownloadModal(false)}>
                <X size={18} />
              </button>
            </div>
            
            <div className="modal-body">
              {isPollingStatus ? (
                /* Show progress when download is running */
                <div className="download-progress">
                  <div className="progress-header">
                    <span className="status-running">
                      <RefreshCw size={16} className="spinning" /> Downloading NSE data...
                    </span>
                  </div>
                  
                  <div className="progress-bar-container">
                    <div 
                      className="progress-bar" 
                      style={{ width: `${bulkDownloadStatus?.progress || 0}%` }}
                    />
                  </div>
                  
                  <div className="progress-details">
                    <span>Progress: {bulkDownloadStatus?.progress || 0}%</span>
                    <span>Days: {bulkDownloadStatus?.days_downloaded || 0}</span>
                    <span>{bulkDownloadStatus?.current_date || 'Initializing...'}</span>
                  </div>
                  
                  {bulkDownloadStatus?.start_date && (
                    <div className="date-range">
                      📅 {bulkDownloadStatus.start_date} → {bulkDownloadStatus.end_date}
                    </div>
                  )}
                  
                  <p className="modal-note" style={{marginTop: '16px'}}>
                    Close this modal - download continues in background. Check the header button for progress.
                  </p>
                </div>
              ) : (
                /* Show download options when not running */
                <>
                  <p className="modal-description">
                    Download fresh NSE market data. This will fetch historical bhavcopy data 
                    from NSE archives and update all stock prices and indicators.
                  </p>
                  
                  <div className="download-options">
                    <button 
                      className="download-option-btn primary"
                      onClick={() => handleStartBulkDownload(10)}
                    >
                      <Download size={16} />
                      <span>10 Years Data</span>
                      <small>~3,650 days • Full history</small>
                    </button>
                    
                    <button 
                      className="download-option-btn"
                      onClick={() => handleStartBulkDownload(5)}
                    >
                      <Download size={16} />
                      <span>5 Years Data</span>
                      <small>~1,825 days • Faster</small>
                    </button>
                    
                    <button 
                      className="download-option-btn"
                      onClick={() => handleStartBulkDownload(1)}
                    >
                      <Download size={16} />
                      <span>1 Year Data</span>
                      <small>~250 days • Quick refresh</small>
                    </button>
                  </div>
                  
                  <p className="modal-note">
                    Download runs in background. Modal will close automatically and you can 
                    track progress in the header button.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stock Search Modal */}
      {showStockSearchModal && (
        <Suspense fallback={<LoadingFallback />}>
          <StockSearchModal 
            isOpen={showStockSearchModal} 
            onClose={() => setShowStockSearchModal(false)} 
          />
        </Suspense>
      )}

      <div className="container">
        {stats && <StatsOverview stats={stats} />}

        {/* WEEKLY SWING PICKS - TOP 2 STOCKS FOR THE WEEK */}
        <WeeklySwingPicks onStockClick={handleStockClick} />

        {/* Market Regime Panel */}
        <Suspense fallback={<LoadingFallback />}>
          <MarketRegimePanel onRegimeChange={handleRegimeChange} />
        </Suspense>

        {/* News & Announcements Panel */}
        <Suspense fallback={<LoadingFallback />}>
          <NewsPanel onStockClick={handleStockClick} />
        </Suspense>

        {/* Sector Rotation Analysis Panel */}
        <Suspense fallback={<LoadingFallback />}>
          <SectorAnalysisPanel onSectorSelect={handleStockClick} />
        </Suspense>

        {/* Sector Heatmap */}
        <Suspense fallback={<LoadingFallback />}>
          <SectorHeatmap />
        </Suspense>

        {/* Sector Performance by Period */}
        <Suspense fallback={<LoadingFallback />}>
          <SectorPerformanceGrid onStockClick={handleStockClick} />
        </Suspense>

        {/* Sector Valuation Analysis (Undervalued/Overvalued) */}
        <Suspense fallback={<LoadingFallback />}>
          <SectorValuationPanel onStockClick={handleStockClick} />
        </Suspense>

        {/* Sector Seasonality Heatmap (10-Year Analysis) */}
        <Suspense fallback={<LoadingFallback />}>
          <SeasonalityHeatmap onStockClick={handleStockClick} />
        </Suspense>

        {/* Monthly Sector Guide - Best Sectors by Month */}
        <Suspense fallback={<LoadingFallback />}>
          <MonthlySectorPicks onStockClick={handleStockClick} />
        </Suspense>

        {/* ============== LONG-TERM INVESTING SECTION ============== */}
        <div className="wealth-section">
          <div className="wealth-section-header">
            <div className="wealth-icon">
              <TrendingUp size={28} />
            </div>
            <div className="wealth-text">
              <h2>Long-Term Wealth Creation</h2>
              <p>Multibagger stocks and futuristic sectors for 3-10 year investing</p>
            </div>
          </div>
        </div>

        {/* Multibagger Picks - Long-term Quality Stocks */}
        <Suspense fallback={<LoadingFallback />}>
          <MultibaggerPicks onStockClick={handleStockClick} />
        </Suspense>

        {/* Futuristic Sectors - Emerging High-Growth Themes */}
        <Suspense fallback={<LoadingFallback />}>
          <FuturisticSectors onStockClick={handleStockClick} />
        </Suspense>

        {/* Mode Toggle */}
        <div className="mode-toggle">
          <button
            className={`mode-btn ${enhancedMode === 'basic' ? 'active' : ''}`}
            onClick={() => setEnhancedMode('basic')}
          >
            Basic Mode
          </button>
          <button
            className={`mode-btn ${enhancedMode === 'enhanced' ? 'active' : ''}`}
            onClick={() => setEnhancedMode('enhanced')}
          >
            <Zap size={16} /> Enhanced Mode
          </button>
          <button
            className={`mode-btn ultimate ${enhancedMode === 'ultimate' ? 'active' : ''}`}
            onClick={() => setEnhancedMode('ultimate')}
          >
            <Target size={16} /> Ultimate Mode
          </button>
          <button
            className={`mode-btn elite ${enhancedMode === 'elite' ? 'active' : ''}`}
            onClick={() => setEnhancedMode('elite')}
          >
            <TrendingUp size={16} /> Elite Mode v2.0 (80%+ Win Rate)
          </button>
        </div>

        <div className="controls">
          <div className="button-group">
            <button
              className="button button-primary"
              onClick={handleIngestLatest}
              disabled={loading}
            >
              <Database size={20} />
              Fetch Latest Data
            </button>

            {enhancedMode === 'elite' ? (
              <button
                className="button button-elite"
                onClick={handleRunEliteScreener}
                disabled={loading}
              >
                <TrendingUp size={20} />
                Run Elite Screener (Top 2 Picks)
              </button>
            ) : enhancedMode === 'ultimate' ? (
              <button
                className="button button-ultimate"
                onClick={handleRunUltimateScreener}
                disabled={loading}
              >
                <Target size={20} />
                Run Ultimate Screener
              </button>
            ) : enhancedMode === 'enhanced' ? (
              <button
                className="button button-success"
                onClick={handleRunEnhancedScreener}
                disabled={loading}
              >
                <Zap size={20} />
                Run Enhanced Screener
              </button>
            ) : (
              <button
                className="button button-primary"
                onClick={handleRunScreener}
                disabled={loading}
              >
                <Activity size={20} />
                Run Basic Screener
              </button>
            )}

            <button
              className="button button-secondary"
              onClick={autoFetchAndScreen}
              disabled={loading}
            >
              <RefreshCw size={20} className={loading ? 'spinning' : ''} />
              {loading ? 'Refreshing...' : 'Refresh & Screen'}
            </button>

            <button
              className="button button-info"
              onClick={() => setShowScoreExplanation(true)}
            >
              <HelpCircle size={20} />
              How Scores Work
            </button>
          </div>

          <Suspense fallback={<LoadingFallback />}>
            <DateSelector
              selectedDate={selectedDate}
              onDateChange={setSelectedDate}
            />
          </Suspense>
        </div>

        {/* Filter Stats */}
        {filterStats && enhancedMode !== 'basic' && (
          <div className={`filter-stats ${enhancedMode === 'ultimate' ? 'ultimate' : ''}`}>
            <h4><Filter size={16} /> {enhancedMode === 'ultimate' ? 'Ultimate' : 'Enhanced'} Filters Applied</h4>
            <div className="filter-badges">
              {filterStats.filters_applied?.map((filter, idx) => (
                <span key={idx} className="filter-badge">{filter}</span>
              ))}
            </div>
            <div className="filter-summary">
              <span>Analyzed: {filterStats.stats?.total_stocks || filterStats.stats?.total_stocks_analyzed || 0}</span>
              <span>Passed: {filterStats.candidates?.length || 0}</span>
              <span>Avg Score: {filterStats.stats?.avg_score?.toFixed(1) || 'N/A'}</span>
            </div>
            {filterStats.sector_analysis?.top_sectors?.length > 0 && (
              <div className="hot-sectors-inline">
                <strong>Top Sectors:</strong> {filterStats.sector_analysis.top_sectors.join(', ')}
              </div>
            )}
            {filterStats.sector_rotation?.hot_sectors?.length > 0 && (
              <div className="hot-sectors-inline">
                <strong>Hot Sectors:</strong> {filterStats.sector_rotation.hot_sectors.join(', ')}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="error">
            <AlertTriangle size={18} style={{ marginRight: '0.5rem' }} />
            {error}
          </div>
        )}
        {success && <div className="success">{success}</div>}

        {loading && (
          <div className="loading">
            <RefreshCw size={24} className="spinning" style={{ marginRight: '0.5rem' }} />
            {autoRefreshStatus || 'Processing...'}
          </div>
        )}

        {!loading && candidates.length > 0 && (
          <div className="results-section">
            <h2>
              <TrendingUp size={24} style={{ display: 'inline', marginRight: '0.5rem' }} />
              {enhancedMode === 'ultimate' ? 'Pattern-Confirmed ' : enhancedMode === 'enhanced' ? 'High-Quality ' : ''}Swing Trade Candidates
              {selectedDate && <span className="date-label"> - {selectedDate}</span>}
            </h2>
            <p className="results-subtitle">
              {enhancedMode === 'ultimate'
                ? 'Filtered by: Candlestick patterns, Supertrend, ADX trend, Sector rotation, Volume'
                : enhancedMode === 'enhanced'
                ? 'Filtered for higher win rate: Market regime, sector rotation, support proximity, and more'
                : 'Click on any stock to view detailed chart and analysis'
              }
            </p>
            <div className="candidates-grid">
              {candidates.map((candidate, index) => (
                <CandidateCard
                  key={candidate.symbol}
                  candidate={candidate}
                  rank={index + 1}
                  onClick={handleStockClick}
                  showPatterns={enhancedMode === 'ultimate'}
                />
              ))}
            </div>
          </div>
        )}

        {!loading && candidates.length === 0 && (
          <div className="loading">
            No candidates found. Click "Fetch Latest Data" to download NSE data and run the screener.
            {enhancedMode !== 'basic' && (
              <p style={{ marginTop: '1rem', fontSize: '0.9rem' }}>
                {enhancedMode === 'ultimate'
                  ? 'Ultimate mode requires pattern + trend confirmation. Try Enhanced or Basic mode for more candidates.'
                  : 'Enhanced mode has stricter filters. Try Basic Mode for more candidates.'
                }
              </p>
            )}
          </div>
        )}

        <Suspense fallback={<LoadingFallback />}>
          <BacktestPanel />
        </Suspense>
      </div>

      {/* Stock Detail Modal */}
      {selectedStock && (
        <StockDetailModal
          symbol={selectedStock}
          onClose={() => setSelectedStock(null)}
        />
      )}

      {/* Score Explanation Modal */}
      {showScoreExplanation && (
        <Suspense fallback={<LoadingFallback />}>
          <ScoreExplanation onClose={() => setShowScoreExplanation(false)} />
        </Suspense>
      )}
    </div>
  );
}

export default App;
