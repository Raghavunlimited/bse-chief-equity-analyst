import React, { useEffect, useState } from 'react';
import { deskAPI } from '../services/api';
import ProvenanceBadge from './ProvenanceBadge';
import SignalAvailabilityBanner from './SignalAvailabilityBanner';

export default function SignalHistory({ category, onOpen }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState(true);
  const [ledgerAvailability, setLedgerAvailability] = useState(null);
  const [filteredDemo, setFilteredDemo] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    deskAPI
      .platformSignals({ category, history, limit: 80 })
      .then((res) => {
        if (!cancelled) {
          setRows(res.data.signals || []);
          setLedgerAvailability(res.data.ledger_availability || null);
          setFilteredDemo(Number(res.data.filtered_demo_rows) || 0);
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
        Admin-published research notes only (append-only). Consultant desk calls
        are not auto-written here. Revisions create a new record; prior rows stay
        for audit. Research only — not orders.
      </p>
      {loading ? <p className="empty-state">Loading ledger…</p> : null}
      {error ? <p className="auth-error">{error}</p> : null}
      {!loading && !error && rows.length === 0 ? (
        <SignalAvailabilityBanner
          availability={
            ledgerAvailability || {
              code: filteredDemo > 0 ? 'ledger_demo_filtered' : 'ledger_empty',
              label:
                filteredDemo > 0
                  ? 'Legacy demo ledger rows are hidden'
                  : 'No published ledger signals for this desk',
              detail:
                filteredDemo > 0
                  ? `${filteredDemo} demo row(s) filtered. Publish with non-demo data_mode (live/delayed/eod). seed_platform is retired.`
                  : 'Ask an admin to publish a research note. seed_platform is retired and will not fill this ledger.',
              boundary:
                'Research only — not an order instruction and not a return guarantee.',
            }
          }
        />
      ) : null}
      {!loading && !error && rows.length > 0 && ledgerAvailability ? (
        <SignalAvailabilityBanner availability={ledgerAvailability} />
      ) : null}
      <ul className="signal-history__list">
        {rows.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className="signal-history__row"
              onClick={() => onOpen?.(s)}
            >
              <span className={`dir dir--${s.direction || s.side || 'none'}`}>
                {String(s.direction || s.side || 'none').toUpperCase()}
              </span>
              <strong>{s.instrument || s.symbol}</strong>
              <span className="muted">{s.desk || category}</span>
              <span className="muted">{s.strategy || s.methodology_id}</span>
              <span className="muted">{s.status}</span>
              <span className="muted">rev {s.revision}</span>
              <ProvenanceBadge
                dataMode={s.data_mode}
                marketDataState={s.data_status}
                compact
              />
              <span className="muted" title="Data source">
                {s.data_source || '—'}
              </span>
              <span className="muted">
                {(s.data_timestamp || s.created_at || '').slice(0, 16)}
              </span>
            </button>
            <p className="signal-history__meta muted">
              Gate: {s.gate_result?.label || 'Admin-published (not auto-gated)'}
            </p>
            <p className="signal-history__rationale">{s.rationale}</p>
            {s.risk_notes ? <p className="signal-history__risk">{s.risk_notes}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
