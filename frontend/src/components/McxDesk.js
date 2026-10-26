import React, { useCallback, useEffect, useRef, useState } from 'react';
import { deskAPI } from '../services/api';
import SignalBoard from './SignalBoard';

export default function McxDesk({ onAnalyze }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await deskAPI.getMcxDesk();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'MCX feed failed');
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

  return (
    <section className="section live-desk" id="section-mcx">
      <div className="section__head">
        <div>
          <h3>Commodities · global futures proxy</h3>
          <p className="section-sub">
            Yahoo continuous futures (usually USD) + USDINR context — not
            exchange-listed MCX INR contracts. Related MCX names are unvalidated
            hints. No lot sizing. Research only.
          </p>
        </div>
        <div className="live-desk__controls">
          <span className="live-pill is-proxy">GLOBAL PROXY</span>
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
      {loading && !data && <p className="muted">Loading commodities…</p>}

      <SignalBoard
        signals={signals}
        desk="mcx"
        source={data?._source}
        availability={data?.signal_availability}
        loading={loading && !data}
        onAnalyze={onAnalyze}
        currency={false}
        emptyMessage="No MCX calls on the board."
        className="sig-grid--mcx-wrap"
      />

      <p className="muted capital-desk__disclaimer">{data?.disclaimer}</p>
    </section>
  );
}
