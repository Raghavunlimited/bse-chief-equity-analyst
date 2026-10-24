import React, { useEffect, useState } from 'react';
import { deskAPI } from '../services/api';
import ProvenanceBadge from './ProvenanceBadge';

export default function SignalHistory({ category, onOpen }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    deskAPI
      .platformSignals({ category, history, limit: 80 })
      .then((res) => {
        if (!cancelled) {
          setRows(res.data.signals || []);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.response?.data?.detail || e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, history]);

  return (
    <section className="signal-history" aria-label="Signal history">
      <div className="signal-history__head">
        <h3>Signal ledger</h3>
        <label className="signal-history__toggle">
          <input
            type="checkbox"
            checked={history}
            onChange={(e) => setHistory(e.target.checked)}
          />
          Include expired / revised
        </label>
      </div>
      <p className="signal-history__note">
        Published signals are append-only. Revisions create a new record; prior rows stay for audit.
      </p>
      {loading ? <p className="empty-state">Loading ledger…</p> : null}
      {error ? <p className="auth-error">{error}</p> : null}
      {!loading && !error && rows.length === 0 ? (
        <p className="empty-state">No signals yet for this desk. Ask an admin to publish, or run seed_platform.</p>
      ) : null}
      <ul className="signal-history__list">
        {rows.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className="signal-history__row"
              onClick={() => onOpen?.(s)}
            >
              <span className={`dir dir--${s.direction}`}>{s.direction.toUpperCase()}</span>
              <strong>{s.symbol}</strong>
              <span className="muted">{s.status}</span>
              <span className="muted">rev {s.revision}</span>
              <ProvenanceBadge dataMode={s.data_mode} compact />
              <span className="muted">{(s.created_at || '').slice(0, 16)}</span>
            </button>
            <p className="signal-history__rationale">{s.rationale}</p>
            {s.risk_notes ? <p className="signal-history__risk">{s.risk_notes}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
