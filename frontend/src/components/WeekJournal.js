import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { deskAPI } from '../services/api';

const LS_KEY = 'swing_desk_journal';

function loadLocal(week) {
  try {
    const all = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
    return all[week] || {};
  } catch {
    return {};
  }
}

function saveLocal(week, symbol, entry) {
  try {
    const all = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
    all[week] = { ...(all[week] || {}), [symbol]: entry };
    localStorage.setItem(LS_KEY, JSON.stringify(all));
  } catch {
    /* ignore */
  }
}

export default function WeekJournal({
  weekLabel,
  candidates = [],
  picks,
  focusSymbol,
  onFocusConsumed,
}) {
  const week = weekLabel || '—';
  const [entries, setEntries] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState(null);
  const [okMsg, setOkMsg] = useState(null);
  const [manualSym, setManualSym] = useState('');
  const [highlight, setHighlight] = useState(null);

  const hydrate = useCallback(async () => {
    if (!week || week === '—') return;
    setError(null);
    const local = loadLocal(week);
    try {
      const { data } = await deskAPI.getJournal(week);
      const list = data.entries || [];
      setEntries(list);
      const map = { ...local };
      list.forEach((e) => {
        const sym = e.symbol;
        map[sym] = {
          invested: !!e.invested,
          capital_deployed: e.capital_deployed ?? '',
          pnl_rupees: e.pnl_rupees ?? '',
          pnl_pct: e.pnl_pct ?? '',
          notes: e.notes || '',
        };
      });
      setDrafts(map);
    } catch {
      setEntries([]);
      setDrafts(local);
    }
  }, [week]);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!focusSymbol) return;
    const sym = String(focusSymbol).toUpperCase();
    setHighlight(sym);
    setDrafts((d) => ({
      ...d,
      [sym]: {
        invested: true,
        capital_deployed: d[sym]?.capital_deployed ?? '',
        pnl_rupees: d[sym]?.pnl_rupees ?? '',
        pnl_pct: d[sym]?.pnl_pct ?? '',
        notes: d[sym]?.notes ?? '',
      },
    }));
    requestAnimationFrame(() => {
      document.getElementById('section-journal')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
      document.getElementById(`journal-${sym}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    });
    const t = window.setTimeout(() => setHighlight(null), 2800);
    onFocusConsumed?.();
    return () => window.clearTimeout(t);
  }, [focusSymbol, onFocusConsumed]);

  const symbols = useMemo(() => {
    const pickList = (candidates && candidates.length ? candidates : picks) || [];
    return Array.from(
      new Set([
        ...pickList.map((c) => c.symbol),
        ...Object.keys(drafts),
        ...entries.map((e) => e.symbol),
      ]),
    );
  }, [candidates, picks, drafts, entries]);

  const setDraft = (sym, patch) => {
    setDrafts((d) => ({ ...d, [sym]: { ...(d[sym] || {}), ...patch } }));
  };

  const addManual = () => {
    const sym = manualSym.trim().toUpperCase().replace(/\s+/g, '');
    if (!sym) return;
    setDraft(sym, {
      invested: true,
      capital_deployed: drafts[sym]?.capital_deployed ?? '',
      pnl_rupees: drafts[sym]?.pnl_rupees ?? '',
      pnl_pct: drafts[sym]?.pnl_pct ?? '',
      notes: drafts[sym]?.notes ?? '',
    });
    setManualSym('');
  };

  const save = async (sym) => {
    const d = drafts[sym] || {};
    const localEntry = {
      invested: !!d.invested,
      capital_deployed: d.capital_deployed === '' ? '' : Number(d.capital_deployed),
      pnl_rupees: d.pnl_rupees === '' ? '' : Number(d.pnl_rupees),
      pnl_pct: d.pnl_pct === '' ? '' : Number(d.pnl_pct),
      notes: d.notes || '',
    };
    saveLocal(week, sym, localEntry);
    setSaving(sym);
    setError(null);
    setOkMsg(null);
    try {
      await deskAPI.saveJournal({
        week,
        symbol: sym,
        invested: localEntry.invested,
        capital_deployed:
          localEntry.capital_deployed === '' ? null : localEntry.capital_deployed,
        pnl_rupees: localEntry.pnl_rupees === '' ? null : localEntry.pnl_rupees,
        pnl_pct: localEntry.pnl_pct === '' ? null : localEntry.pnl_pct,
        notes: localEntry.notes,
      });
      await hydrate();
      setOkMsg(`${sym} saved for ${week}`);
      window.setTimeout(() => setOkMsg(null), 2500);
    } catch (e) {
      setError(
        e.response?.data?.detail ||
          e.message ||
          'API unavailable — kept in this browser (localStorage)',
      );
    } finally {
      setSaving(null);
    }
  };

  const investedCount = symbols.filter((s) => drafts[s]?.invested).length;
  const runningPnl = symbols.reduce((acc, sym) => {
    const d = drafts[sym];
    if (d?.invested && d.pnl_rupees !== '' && d.pnl_rupees != null) {
      return acc + Number(d.pnl_rupees);
    }
    return acc;
  }, 0);

  return (
    <section className="section week-journal" id="section-journal">
      <div className="section__head">
        <div>
          <h3>Week journal</h3>
          <p className="section-sub">
            Week <strong className="week-inline">{week}</strong> — tick “I took this trade”,
            enter amount deployed, and log P&amp;L (₹ or %). Saved to the desk API, with
            localStorage fallback.
          </p>
        </div>
        <div className="week-journal__pnl">
          <span>
            {investedCount} taken · Running P&amp;L
          </span>
          <strong className={runningPnl >= 0 ? 'pos' : 'neg'}>
            {runningPnl >= 0 ? '+' : ''}
            ₹{runningPnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </strong>
        </div>
      </div>

      <div className="journal-add">
        <input
          type="text"
          value={manualSym}
          onChange={(e) => setManualSym(e.target.value)}
          placeholder="Add symbol (e.g. RELIANCE)"
          onKeyDown={(e) => {
            if (e.key === 'Enter') addManual();
          }}
          aria-label="Add journal symbol"
        />
        <button type="button" className="btn ghost" onClick={addManual}>
          Add row
        </button>
      </div>

      {error && (
        <p className="error-text">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </p>
      )}
      {okMsg && <p className="ok-text">{okMsg}</p>}

      {symbols.length === 0 && (
        <p className="muted">
          No symbols yet — apply the Week Planner above, or add a ticker you already traded.
        </p>
      )}

      <div className="journal-list">
        {symbols.map((sym) => {
          const d = drafts[sym] || {};
          const invested = !!d.invested;
          return (
            <div
              key={sym}
              className={`journal-row ${invested ? 'journal-row--on' : ''} ${
                highlight === sym ? 'journal-row--focus' : ''
              }`}
              id={`journal-${sym}`}
            >
              <div className="journal-row__sym">
                <strong>{sym}</strong>
                <label className="journal-check">
                  <input
                    type="checkbox"
                    checked={invested}
                    onChange={(e) => setDraft(sym, { invested: e.target.checked })}
                  />
                  I took this trade
                </label>
              </div>
              <label>
                Deployed ₹
                <input
                  type="number"
                  disabled={!invested}
                  value={d.capital_deployed ?? ''}
                  onChange={(e) => setDraft(sym, { capital_deployed: e.target.value })}
                  placeholder="0"
                />
              </label>
              <label>
                P&amp;L ₹
                <input
                  type="number"
                  disabled={!invested}
                  value={d.pnl_rupees ?? ''}
                  onChange={(e) => setDraft(sym, { pnl_rupees: e.target.value })}
                  placeholder="0"
                />
              </label>
              <label>
                P&amp;L %
                <input
                  type="number"
                  step="0.1"
                  disabled={!invested}
                  value={d.pnl_pct ?? ''}
                  onChange={(e) => setDraft(sym, { pnl_pct: e.target.value })}
                  placeholder="0"
                />
              </label>
              <label className="journal-notes">
                Notes
                <input
                  type="text"
                  disabled={!invested}
                  value={d.notes ?? ''}
                  onChange={(e) => setDraft(sym, { notes: e.target.value })}
                  placeholder="Optional"
                />
              </label>
              <button
                type="button"
                className="btn primary"
                disabled={saving === sym || week === '—'}
                onClick={() => save(sym)}
              >
                {saving === sym ? 'Saving…' : 'Save'}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
