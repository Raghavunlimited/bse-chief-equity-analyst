import React, { useState } from 'react';
import { screenerAPI } from '../services/api';
import { BarChart3 } from 'lucide-react';

function BacktestPanel() {
  const [backtestParams, setBacktestParams] = useState({
    startDate: '2025-09-16',
    endDate: '2026-02-12',
    capital: 1000000,
    maxPositions: 10
  });

  const [backtestResults, setBacktestResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleRunBacktest = async () => {
    try {
      setLoading(true);
      setError(null);

      const results = await screenerAPI.runBacktest(
        backtestParams.startDate,
        backtestParams.endDate,
        backtestParams.capital,
        backtestParams.maxPositions
      );

      setBacktestResults(results);
    } catch (err) {
      setError('Backtest failed: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="backtest-section">
      <h2>
        <BarChart3 size={24} style={{ display: 'inline', marginRight: '0.5rem' }} />
        Backtest Strategy
      </h2>

      <div className="backtest-form">
        <div className="form-group">
          <label>Start Date</label>
          <input
            type="date"
            value={backtestParams.startDate}
            onChange={(e) => setBacktestParams({ ...backtestParams, startDate: e.target.value })}
          />
        </div>

        <div className="form-group">
          <label>End Date</label>
          <input
            type="date"
            value={backtestParams.endDate}
            onChange={(e) => setBacktestParams({ ...backtestParams, endDate: e.target.value })}
          />
        </div>

        <div className="form-group">
          <label>Capital (₹)</label>
          <input
            type="number"
            value={backtestParams.capital}
            onChange={(e) => setBacktestParams({ ...backtestParams, capital: Number(e.target.value) })}
          />
        </div>

        <div className="form-group">
          <label>Max Positions</label>
          <input
            type="number"
            value={backtestParams.maxPositions}
            onChange={(e) => setBacktestParams({ ...backtestParams, maxPositions: Number(e.target.value) })}
          />
        </div>
      </div>

      <button
        className="button button-primary"
        onClick={handleRunBacktest}
        disabled={loading}
      >
        <BarChart3 size={20} />
        {loading ? 'Running Backtest...' : 'Run Backtest'}
      </button>

      {error && <div className="error" style={{ marginTop: '1rem' }}>{error}</div>}

      {backtestResults && (
        <div className="backtest-results" style={{ marginTop: '2rem' }}>
          <div className="backtest-stat">
            <div className="label">Total Trades</div>
            <div className="value">{backtestResults.total_trades}</div>
          </div>

          <div className="backtest-stat">
            <div className="label">Win Rate</div>
            <div className="value" style={{ color: backtestResults.win_rate >= 50 ? '#34d399' : '#f87171' }}>
              {backtestResults.win_rate.toFixed(2)}%
            </div>
          </div>

          <div className="backtest-stat">
            <div className="label">Avg Return</div>
            <div className="value" style={{ color: backtestResults.avg_return >= 0 ? '#34d399' : '#f87171' }}>
              {backtestResults.avg_return.toFixed(2)}%
            </div>
          </div>

          <div className="backtest-stat">
            <div className="label">Median Return</div>
            <div className="value">{backtestResults.median_return.toFixed(2)}%</div>
          </div>

          <div className="backtest-stat">
            <div className="label">Best Trade</div>
            <div className="value positive">{backtestResults.best_trade.toFixed(2)}%</div>
          </div>

          <div className="backtest-stat">
            <div className="label">Worst Trade</div>
            <div className="value negative">{backtestResults.worst_trade.toFixed(2)}%</div>
          </div>

          <div className="backtest-stat">
            <div className="label">Profit Factor</div>
            <div className="value">
              {backtestResults.profit_factor === Infinity ? '∞' : backtestResults.profit_factor.toFixed(2)}
            </div>
          </div>

          <div className="backtest-stat">
            <div className="label">Target Hit Rate</div>
            <div className="value positive">{backtestResults.target_hit_rate.toFixed(2)}%</div>
          </div>

          <div className="backtest-stat">
            <div className="label">Stop Hit Rate</div>
            <div className="value negative">{backtestResults.stop_hit_rate.toFixed(2)}%</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BacktestPanel;
