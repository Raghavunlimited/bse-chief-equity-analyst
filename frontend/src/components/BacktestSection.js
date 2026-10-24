import React, { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { deskAPI } from '../services/api';

export default function BacktestSection() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await deskAPI.runBacktest({});
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const stats = result?.stats;

  return (
    <section className="section backtest-section">
      <div className="section__head">
        <div>
          <h3>Backtest</h3>
          <p>Same weekly strategy as live picks. Costs and gap fills included.</p>
        </div>
        <button type="button" className="btn primary" onClick={run} disabled={loading}>
          {loading ? 'Running…' : 'Run backtest'}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {stats && (
        <>
          <div className="stat-grid">
            <div>
              <span>Weeks</span>
              <strong>{stats.weeks}</strong>
            </div>
            <div>
              <span>Cash weeks</span>
              <strong>{stats.cash_week_pct}%</strong>
            </div>
            <div>
              <span>Trades</span>
              <strong>{stats.trades}</strong>
            </div>
            <div>
              <span>Win rate</span>
              <strong>{stats.win_rate}%</strong>
            </div>
            <div>
              <span>Avg week</span>
              <strong>{stats.avg_week_return_pct}%</strong>
            </div>
            <div>
              <span>Max DD</span>
              <strong className="neg">{stats.max_drawdown_pct}%</strong>
            </div>
            <div>
              <span>Total return</span>
              <strong className={stats.total_return_pct >= 0 ? 'pos' : 'neg'}>
                {stats.total_return_pct}%
              </strong>
            </div>
            <div>
              <span>Profit factor</span>
              <strong>{stats.profit_factor ?? '—'}</strong>
            </div>
          </div>

          {result.equity_curve?.length > 1 && (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={result.equity_curve}>
                  <defs>
                    <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#E8A838" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#E8A838" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#8B93A7', fontSize: 10 }}
                    minTickGap={50}
                  />
                  <YAxis
                    tick={{ fill: '#8B93A7', fontSize: 10 }}
                    width={70}
                    tickFormatter={(v) => `${(v / 1e5).toFixed(1)}L`}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#141A22',
                      border: '1px solid #2A3340',
                      borderRadius: 8,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#E8A838"
                    fill="url(#eqFill)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </section>
  );
}
