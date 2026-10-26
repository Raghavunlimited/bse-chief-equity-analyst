import React, { useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

const empty = {
  symbol: 'RELIANCE',
  category: 'swing',
  direction: 'none',
  timeframe: '1w',
  rationale: '',
  data_mode: 'delayed',
  expires_in_hours: 168,
};

export default function AdminPanel({ open, onClose }) {
  const [instruments, setInstruments] = useState([]);
  const [audit, setAudit] = useState([]);
  const [form, setForm] = useState(empty);
  const [instForm, setInstForm] = useState({
    symbol: '',
    category: 'swing',
    name: '',
    market: 'NSE',
  });
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!open) return;
    deskAPI
      .adminInstruments()
      .then((r) => setInstruments(r.data.instruments || []))
      .catch((e) => setErr(e.response?.data?.detail || e.message));
    deskAPI
      .adminAudit(40)
      .then((r) => setAudit(r.data.entries || []))
      .catch(() => {});
  }, [open]);

  if (!open) return null;

  async function publish(e) {
    e.preventDefault();
    setMsg(null);
    setErr(null);
    try {
      const { data } = await deskAPI.adminPublishSignal({
        ...form,
        rationale:
          form.rationale ||
          'Admin-published research note. Insufficient conviction defaults to none.',
        risk_notes:
          'Research only — not a guarantee of returns. Verify independently. DEMO unless labeled otherwise.',
      });
      setMsg(`Published ${data.symbol} ${data.direction} (${data.id.slice(0, 8)}…)`);
    } catch (ex) {
      setErr(ex.response?.data?.detail || ex.message);
    }
  }

  async function saveInstrument(e) {
    e.preventDefault();
    setErr(null);
    try {
      await deskAPI.adminUpsertInstrument(instForm);
      const r = await deskAPI.adminInstruments();
      setInstruments(r.data.instruments || []);
      setMsg(`Instrument ${instForm.symbol} saved`);
    } catch (ex) {
      setErr(ex.response?.data?.detail || ex.message);
    }
  }

  return (
    <div className="admin-drawer" role="dialog" aria-label="Admin">
      <div className="admin-drawer__panel">
        <header className="admin-drawer__head">
          <h2>Admin</h2>
          <button type="button" onClick={onClose} aria-label="Close admin">
            Close
          </button>
        </header>
        <p className="admin-disclosure">
          Changes are audited. Prefer data_mode=demo unless a live provider is wired and verified.
        </p>
        {msg ? <p className="admin-ok">{msg}</p> : null}
        {err ? <p className="auth-error">{String(err)}</p> : null}

        <h3>Publish signal</h3>
        <form className="admin-form" onSubmit={publish}>
          <label>
            Symbol
            <input
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              required
            />
          </label>
          <label>
            Category
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              <option value="swing">swing</option>
              <option value="intraday">intraday</option>
              <option value="commodity">commodity</option>
            </select>
          </label>
          <label>
            Direction
            <select
              value={form.direction}
              onChange={(e) => setForm({ ...form, direction: e.target.value })}
            >
              <option value="none">none (no actionable signal)</option>
              <option value="buy">buy</option>
              <option value="sell">sell</option>
            </select>
          </label>
          <label>
            Data mode
            <select
              value={form.data_mode}
              onChange={(e) => setForm({ ...form, data_mode: e.target.value })}
            >
              <option value="delayed">delayed</option>
              <option value="stale">stale</option>
              <option value="live">live</option>
            </select>
          </label>
          <label>
            Rationale
            <textarea
              value={form.rationale}
              onChange={(e) => setForm({ ...form, rationale: e.target.value })}
              rows={3}
              required
            />
          </label>
          <button type="submit">Publish (append-only)</button>
        </form>

        <h3>Instruments</h3>
        <form className="admin-form" onSubmit={saveInstrument}>
          <label>
            Symbol
            <input
              value={instForm.symbol}
              onChange={(e) =>
                setInstForm({ ...instForm, symbol: e.target.value.toUpperCase() })
              }
              required
            />
          </label>
          <label>
            Name
            <input
              value={instForm.name}
              onChange={(e) => setInstForm({ ...instForm, name: e.target.value })}
            />
          </label>
          <label>
            Category
            <select
              value={instForm.category}
              onChange={(e) => setInstForm({ ...instForm, category: e.target.value })}
            >
              <option value="swing">swing</option>
              <option value="intraday">intraday</option>
              <option value="commodity">commodity</option>
            </select>
          </label>
          <button type="submit">Save instrument</button>
        </form>
        <ul className="admin-inst-list">
          {instruments.map((i) => (
            <li key={i.id}>
              {i.symbol} · {i.category} · {i.is_active ? 'active' : 'off'}
            </li>
          ))}
        </ul>

        <h3>Audit (recent)</h3>
        <ul className="admin-audit">
          {audit.map((a) => (
            <li key={a.id}>
              <code>{a.created_at?.slice(0, 19)}</code> {a.action} {a.entity_type}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
