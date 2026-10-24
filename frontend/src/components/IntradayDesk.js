import React, { useCallback, useEffect, useRef, useState } from 'react';
import { deskAPI } from '../services/api';
import SignalBoard from './SignalBoard';

export default function IntradayDesk({ onOpen, onAnalyze }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await deskAPI.getIntradayDesk(20);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Intraday feed failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [load]);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!live) return undefined;
    const sec = Math.max(10, data?.poll_seconds || 15) * 1000;
    timer.current = setInterval(load, sec);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [live, load, data?.poll_seconds]);

  const signals = data?.signals || data?.calls || [];
  const session = data?.session || {};
  const buys = signals.filter((s) => {
    const side = String(s.side || '').toUpperCase();
    return side === 'BUY' || side === 'LONG';
  }).length;
  const sells = signals.filter((s) => {
    const side = String(s.side || '').toUpperCase();
    return side === 'SELL' || side === 'SHORT';
  }).length;

  return (
    <section className="section live-desk" id="section-intraday">
      <div className="section__head">
        <div>
          <h3>Intraday tape</h3>
          <p className="section-sub">
            Near-live NSE cash bias — consultant BUY/SELL/HOLD when available.
            Risk 0.25–0.5% per idea. Research only.
          </p>
        </div>
        <div className="live-desk__controls">
          <span
            className={`live-pill ${session.in_session ? 'is-live' : 'is-off'}`}
            title={session.note || ''}
          >
            {session.in_session ? 'SESSION OPEN' : session.pre_market ? 'PRE-OPEN' : 'CLOSED'}
          </span>
          <label className="live-toggle">
            <input
              type="checkbox"
              checked={live}
              onChange={(e) => setLive(e.target.checked)}
            />
            Auto-refresh
          </label>
          <button type="button" className="btn ghost" onClick={load} disabled={loading}>
            Refresh now
          </button>
        </div>
      </div>

      {data?.message && <p className="live-desk__msg">{data.message}</p>}
      {error && <p className="error-text">{String(error)}</p>}

      <div className="stat-grid compact live-desk__stats">
        <div>
          <span>Buys</span>
          <strong className="pos">{data?.buy_count ?? data?.long_count ?? buys}</strong>
        </div>
        <div>
          <span>Sells</span>
          <strong className="neg">{data?.sell_count ?? data?.short_count ?? sells}</strong>
        </div>
        <div>
          <span>Watch</span>
          <strong>{data?.count ?? signals.length ?? '—'}</strong>
        </div>
        <div>
          <span>As of</span>
          <strong className="mono">
            {data?.as_of ? new Date(data.as_of).toLocaleTimeString() : '—'}
          </strong>
        </div>
      </div>

      <SignalBoard
        signals={signals}
        source={data?._source}
        loading={loading && !data}
        onOpen={onOpen}
        onAnalyze={onAnalyze}
        emptyMessage="No intraday calls right now."
      />

      <p className="muted capital-desk__disclaimer">{data?.disclaimer}</p>
    </section>
  );
}
