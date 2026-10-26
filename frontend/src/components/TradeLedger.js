import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

function fmt(n, d = 2) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
}

const emptyTrade = {
  instrument: '',
  direction: 'LONG',
  quantity: '',
  entry_price: '',
  lots: '',
  fees: '0',
  notes: '',
};

export default function TradeLedger() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tradeForm, setTradeForm] = useState(emptyTrade);
  const [capForm, setCapForm] = useState({
    kind: 'deposit',
    amount: '',
    notes: '',
  });
  const [exitDraft, setExitDraft] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { data } = await deskAPI.getLedgerSummary();
      setSummary(data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ledger failed');
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submitCapital = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deskAPI.postLedgerMovement({
        kind: capForm.kind,
        amount: Number(capForm.amount),
        notes: capForm.notes || undefined,
      });
      setCapForm((c) => ({ ...c, amount: '', notes: '' }));
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitTrade = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deskAPI.openLedgerTrade({
        instrument: tradeForm.instrument,
        direction: tradeForm.direction,
        quantity: Number(tradeForm.quantity),
        entry_price: Number(tradeForm.entry_price),
        lots: tradeForm.lots === '' ? undefined : Number(tradeForm.lots),
        fees: Number(tradeForm.fees || 0),
        notes: tradeForm.notes || undefined,
      });
      setTradeForm(emptyTrade);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitExit = async (tradeId) => {
    const d = exitDraft[tradeId] || {};
    setBusy(true);
    setError(null);
    try {
      await deskAPI.exitLedgerTrade(tradeId, {
        quantity: Number(d.quantity),
        price: Number(d.price),
        fees: Number(d.fees || 0),
        notes: d.notes || undefined,
      });
      setExitDraft((x) => ({ ...x, [tradeId]: {} }));
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  const cap = summary?.capital || {};
  const unrl = summary?.estimated_unrealized || {};
  const mark = summary?.estimated_equity_mark || {};

  return (
    <section className="section trade-ledger" id="section-ledger" data-testid="trade-ledger">
      <div className="section__head">
        <div>
          <h3>Trade journal &amp; capital</h3>
          <p className="section-sub">
            User-entered records only — not verified broker executions. Corrections
            keep an audit trail. Unrealized P&amp;L is estimated only when a quote is
            available and is labeled separately from book equity.
          </p>
        </div>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      <p className="banner warn" role="note" data-testid="ledger-disclaimer">
        {summary?.disclaimer ||
          'User-entered research journal only — not verified broker fills.'}
      </p>

      {error && (
        <p className="error-text" role="alert">
          {String(error)}
        </p>
      )}
      {loading && !summary && <p className="muted">Loading ledger…</p>}

      {summary && (
        <div className="trade-ledger__capital" data-testid="ledger-capital">
          <div className="oc-stat">
            <span>Starting capital</span>
            <strong>{fmt(cap.starting_capital)}</strong>
          </div>
          <div className="oc-stat">
            <span>Deposits</span>
            <strong>{fmt(cap.deposits)}</strong>
          </div>
          <div className="oc-stat">
            <span>Withdrawals</span>
            <strong>{fmt(cap.withdrawals)}</strong>
          </div>
          <div className="oc-stat">
            <span>Realized P&amp;L</span>
            <strong className={cap.realized_pnl >= 0 ? 'is-up' : 'is-down'}>
              {fmt(cap.realized_pnl)}
            </strong>
          </div>
          <div className="oc-stat">
            <span>Costs (fees)</span>
            <strong>{fmt(cap.costs_fees_total)}</strong>
          </div>
          <div className="oc-stat">
            <span>Book equity</span>
            <strong>{fmt(cap.book_equity)}</strong>
          </div>
          <div className="oc-stat" title={unrl.note || ''}>
            <span>Est. unrealized</span>
            <strong>
              {unrl.available ? fmt(unrl.total) : 'unavailable'}
            </strong>
            <em className="muted">{unrl.label || 'separate from book'}</em>
          </div>
          <div className="oc-stat" title={mark.note || ''}>
            <span>Est. mark equity</span>
            <strong>{mark.available ? fmt(mark.value) : 'unavailable'}</strong>
          </div>
          <p className="muted trade-ledger__formula">{cap.formula}</p>
        </div>
      )}

      <div className="trade-ledger__forms">
        <form className="trade-ledger__card" onSubmit={submitCapital}>
          <h4>Capital movement</h4>
          <label>
            Kind
            <select
              value={capForm.kind}
              onChange={(e) => setCapForm((c) => ({ ...c, kind: e.target.value }))}
            >
              <option value="starting_capital">Starting capital</option>
              <option value="deposit">Deposit</option>
              <option value="withdrawal">Withdrawal</option>
            </select>
          </label>
          <label>
            Amount
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={capForm.amount}
              onChange={(e) => setCapForm((c) => ({ ...c, amount: e.target.value }))}
            />
          </label>
          <label>
            Notes
            <input
              value={capForm.notes}
              onChange={(e) => setCapForm((c) => ({ ...c, notes: e.target.value }))}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>
            Record movement
          </button>
        </form>

        <form className="trade-ledger__card" onSubmit={submitTrade}>
          <h4>Open position (manual)</h4>
          <label>
            Instrument
            <input
              required
              value={tradeForm.instrument}
              onChange={(e) =>
                setTradeForm((t) => ({ ...t, instrument: e.target.value.toUpperCase() }))
              }
            />
          </label>
          <label>
            Direction
            <select
              value={tradeForm.direction}
              onChange={(e) => setTradeForm((t) => ({ ...t, direction: e.target.value }))}
            >
              <option value="LONG">LONG</option>
              <option value="SHORT">SHORT</option>
            </select>
          </label>
          <label>
            Quantity
            <input
              type="number"
              min="0"
              step="any"
              required
              value={tradeForm.quantity}
              onChange={(e) => setTradeForm((t) => ({ ...t, quantity: e.target.value }))}
            />
          </label>
          <label>
            Entry price
            <input
              type="number"
              min="0"
              step="any"
              required
              value={tradeForm.entry_price}
              onChange={(e) =>
                setTradeForm((t) => ({ ...t, entry_price: e.target.value }))
              }
            />
          </label>
          <label>
            Lots (optional)
            <input
              type="number"
              min="0"
              step="any"
              value={tradeForm.lots}
              onChange={(e) => setTradeForm((t) => ({ ...t, lots: e.target.value }))}
            />
          </label>
          <label>
            Fees
            <input
              type="number"
              min="0"
              step="any"
              value={tradeForm.fees}
              onChange={(e) => setTradeForm((t) => ({ ...t, fees: e.target.value }))}
            />
          </label>
          <label>
            Notes
            <input
              value={tradeForm.notes}
              onChange={(e) => setTradeForm((t) => ({ ...t, notes: e.target.value }))}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>
            Log open trade
          </button>
        </form>
      </div>

      <h4>Open positions</h4>
      {(summary?.open_positions || []).length === 0 && (
        <p className="muted">No open user-entered positions.</p>
      )}
      <ul className="trade-ledger__list">
        {(summary?.open_positions || []).map((t) => (
          <li key={t.id} className="trade-ledger__item">
            <div>
              <strong>
                {t.instrument} {t.direction}
              </strong>{' '}
              qty {fmt(t.quantity, 4)} @ {fmt(t.entry_price)} · fees {fmt(t.fees_total)}
              <div className="muted">
                Unrealized:{' '}
                {t.unrealized?.available
                  ? `${fmt(t.unrealized.estimated_unrealized_pnl)} (${t.unrealized.label})`
                  : `unavailable (${t.unrealized?.reason || 'no quote'})`}
              </div>
            </div>
            <div className="trade-ledger__exit">
              <input
                placeholder="Exit qty"
                type="number"
                value={exitDraft[t.id]?.quantity || ''}
                onChange={(e) =>
                  setExitDraft((x) => ({
                    ...x,
                    [t.id]: { ...(x[t.id] || {}), quantity: e.target.value },
                  }))
                }
              />
              <input
                placeholder="Exit price"
                type="number"
                value={exitDraft[t.id]?.price || ''}
                onChange={(e) =>
                  setExitDraft((x) => ({
                    ...x,
                    [t.id]: { ...(x[t.id] || {}), price: e.target.value },
                  }))
                }
              />
              <input
                placeholder="Fees"
                type="number"
                value={exitDraft[t.id]?.fees || ''}
                onChange={(e) =>
                  setExitDraft((x) => ({
                    ...x,
                    [t.id]: { ...(x[t.id] || {}), fees: e.target.value },
                  }))
                }
              />
              <button
                type="button"
                className="btn ghost"
                disabled={busy}
                onClick={() => submitExit(t.id)}
              >
                Record exit
              </button>
            </div>
          </li>
        ))}
      </ul>

      <h4>Closed (recent)</h4>
      <ul className="trade-ledger__list">
        {(summary?.closed_positions || []).slice(0, 20).map((t) => (
          <li key={t.id} className="trade-ledger__item">
            <strong>
              {t.instrument} {t.direction}
            </strong>{' '}
            realized {fmt(t.realized_pnl)} · fees {fmt(t.fees_total)} · exits{' '}
            {(t.exits || []).length}
          </li>
        ))}
      </ul>
    </section>
  );
}
