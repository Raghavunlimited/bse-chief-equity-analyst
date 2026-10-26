import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deskAPI } from '../services/api';
import OiComparisonChart from './OiComparisonChart';

const UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY'];

function fmt(n, d = 2) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', {
    maximumFractionDigits: d,
    minimumFractionDigits: d > 0 ? Math.min(d, 2) : 0,
  });
}

function pct(n) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  const v = Number(n);
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function BuildupBadge({ buildup }) {
  const label = buildup?.label || 'Unknown';
  const slug = String(label).toLowerCase().replace(/\s+/g, '-');
  return <span className={`oc-buildup oc-buildup--${slug}`}>{label}</span>;
}

function OiBar({ value, max, side }) {
  const pctW = max > 0 && value != null ? Math.min(100, (Number(value) / max) * 100) : 0;
  return (
    <div className={`oc-oi-bar oc-oi-bar--${side}`} title={fmt(value, 0)}>
      <div className="oc-oi-bar__fill" style={{ width: `${pctW}%` }} />
      <span>{fmt(value, 0)}</span>
    </div>
  );
}

export default function OptionChainPanel({ defaultUnderlying = 'NIFTY' }) {
  const [underlying, setUnderlying] = useState(defaultUnderlying);
  const [expiryMode, setExpiryMode] = useState('nearest');
  const [wing, setWing] = useState(15);
  const [data, setData] = useState(null);
  const [oiViz, setOiViz] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(true);
  const timer = useRef(null);

  const loadOiViz = useCallback(async () => {
    try {
      const { data: v } = await deskAPI.getOptionOiViz(underlying);
      setOiViz(v);
    } catch (e) {
      setOiViz({
        available: false,
        status: 'unavailable',
        blocker: e.response?.data?.detail || e.message || 'OI viz request failed',
        signal_disclaimer:
          'Open interest and PCR are descriptive research metrics only — not trade signals.',
        expiries_oi_comparison: [],
      });
    }
  }, [underlying]);

  const load = useCallback(async () => {
    try {
      const { data: d } = await deskAPI.getOptionChain(underlying, {
        activate_if_needed: false,
      });
      setData(d);
      setError(null);
    } catch (e) {
      const status = e.response?.status;
      if (status === 404) {
        setData(null);
        setError(null);
      } else {
        setError(e.response?.data?.detail || e.message || 'Option chain failed');
      }
    }
    await loadOiViz();
  }, [underlying, loadOiViz]);

  const activate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: d } = await deskAPI.activateOptionChain({
        underlying,
        expiry_mode: expiryMode,
        wing,
      });
      setData(d);
      await loadOiViz();
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Activate failed');
      setData(null);
      await loadOiViz();
    } finally {
      setLoading(false);
    }
  }, [underlying, expiryMode, wing, loadOiViz]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!live || !data) return undefined;
    timer.current = setInterval(load, 5000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [live, load, data]);

  const analytics = data?.analytics || {};
  const rows = useMemo(() => data?.rows || [], [data?.rows]);

  const maxOi = useMemo(() => {
    let m = 1;
    rows.forEach((r) => {
      const ce = r.ce?.oi;
      const pe = r.pe?.oi;
      if (ce != null) m = Math.max(m, Number(ce));
      if (pe != null) m = Math.max(m, Number(pe));
    });
    return m;
  }, [rows]);

  return (
    <section className="option-chain" aria-label="Live option chain">
      <div className="option-chain__head">
        <div>
          <h4>Option chain (optional)</h4>
          <p className="section-sub">
            Requires Kotak Neo login + Activate. Idle = unavailable (not zero PCR).
            Greeks / PCR / walls only from a live subscribed chain — no placeholders.
          </p>
        </div>
        <div className="option-chain__controls">
          <select
            value={underlying}
            onChange={(e) => setUnderlying(e.target.value)}
            aria-label="Underlying"
          >
            {UNDERLYINGS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
          <select
            value={expiryMode}
            onChange={(e) => setExpiryMode(e.target.value)}
            aria-label="Expiry mode"
          >
            <option value="nearest">Nearest / weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <select
            value={wing}
            onChange={(e) => setWing(Number(e.target.value))}
            aria-label="Strike wing"
          >
            {[10, 15, 20].map((w) => (
              <option key={w} value={w}>
                ATM ±{w}
              </option>
            ))}
          </select>
          <label className="live-toggle">
            <input
              type="checkbox"
              checked={live}
              onChange={(e) => setLive(e.target.checked)}
            />
            Live
          </label>
          <button type="button" className="btn" onClick={activate} disabled={loading}>
            {loading ? 'Subscribing…' : data ? 'Re-subscribe' : 'Activate chain'}
          </button>
          <button type="button" className="btn ghost" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="banner warn" role="alert">
          <strong>Option chain</strong>
          <p>{typeof error === 'string' ? error : JSON.stringify(error)}</p>
          <p className="muted">
            Requires Kotak session (`POST /api/kotak/session/login`) — no demo chain.
          </p>
        </div>
      )}

      {!data && !error && (
        <div className="banner warn" role="status" data-testid="option-chain-unavailable">
          <strong>Unavailable</strong>
          <p>
            No active chain for {underlying}. PCR, walls, and Greeks are not shown
            as zeros — activate after Kotak session login. Provider is Kotak Neo WS
            only (not e2e-verified in CI).
          </p>
        </div>
      )}

      <OiComparisonChart viz={oiViz} />

      {data && (
        <>
          <div className="option-chain__meta">
            <div className="oc-stat">
              <span>Spot</span>
              <strong>{data.spot != null ? fmt(data.spot) : 'unavailable'}</strong>
            </div>
            <div className="oc-stat">
              <span>ATM</span>
              <strong>{data.atm != null ? fmt(data.atm, 0) : 'unavailable'}</strong>
            </div>
            <div className="oc-stat">
              <span>Expiry</span>
              <strong>{data.expiry || '—'}</strong>
            </div>
            <div className="oc-stat" title="Descriptive research metric — not a trade signal">
              <span>Total OI-PCR</span>
              <strong>
                {analytics.total_oi_pcr != null ? fmt(analytics.total_oi_pcr, 3) : 'unavailable'}
              </strong>
              <em className={`oc-regime oc-regime--${String(analytics.pcr_regime || '').toLowerCase()}`}>
                {analytics.pcr_regime || '—'}
              </em>
            </div>
            <div className="oc-stat">
              <span>ATM-PCR (±5)</span>
              <strong>
                {analytics.atm_pcr != null ? fmt(analytics.atm_pcr, 3) : 'unavailable'}
              </strong>
            </div>
            <div className="oc-stat">
              <span>Vol-PCR</span>
              <strong>
                {analytics.volume_pcr != null ? fmt(analytics.volume_pcr, 3) : 'unavailable'}
              </strong>
            </div>
            <div className="oc-stat">
              <span>Max Pain</span>
              <strong>
                {analytics.max_pain != null ? fmt(analytics.max_pain, 0) : 'unavailable'}
              </strong>
            </div>
            <div className="oc-stat">
              <span>Call Wall</span>
              <strong className="is-down">
                {analytics.call_wall != null ? fmt(analytics.call_wall, 0) : 'unavailable'}
              </strong>
            </div>
            <div className="oc-stat">
              <span>Put Wall</span>
              <strong className="is-up">
                {analytics.put_wall != null ? fmt(analytics.put_wall, 0) : 'unavailable'}
              </strong>
            </div>
            <div className="oc-stat">
              <span>ATM Straddle</span>
              <strong>
                {analytics.atm_straddle_premium != null
                  ? fmt(analytics.atm_straddle_premium)
                  : 'unavailable'}
              </strong>
            </div>
            {data.future?.buildup && (
              <div className="oc-stat">
                <span>Futures OI</span>
                <BuildupBadge buildup={data.future.buildup} />
              </div>
            )}
          </div>
          <p className="muted">
            PCR / walls / buildup are descriptive only — not standalone trading signals.
          </p>

          <div className="option-chain__table-wrap">
            <table className="option-chain__table">
              <thead>
                <tr>
                  <th colSpan={8} className="oc-side oc-side--ce">
                    CALLS
                  </th>
                  <th className="oc-strike-h">Strike</th>
                  <th colSpan={8} className="oc-side oc-side--pe">
                    PUTS
                  </th>
                </tr>
                <tr>
                  <th>Buildup</th>
                  <th>IV</th>
                  <th>Δ</th>
                  <th>LTP</th>
                  <th>Chg%</th>
                  <th>OI</th>
                  <th>OI Δ</th>
                  <th>Bid/Ask</th>
                  <th />
                  <th>Bid/Ask</th>
                  <th>OI Δ</th>
                  <th>OI</th>
                  <th>Chg%</th>
                  <th>LTP</th>
                  <th>Δ</th>
                  <th>IV</th>
                  <th>Buildup</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const ce = r.ce || {};
                  const pe = r.pe || {};
                  const isAtm = r.atm;
                  const isWallCe = analytics.call_wall === r.strike;
                  const isWallPe = analytics.put_wall === r.strike;
                  const isPain = analytics.max_pain === r.strike;
                  return (
                    <tr
                      key={r.strike}
                      className={[
                        isAtm ? 'is-atm' : '',
                        isPain ? 'is-max-pain' : '',
                        isWallCe || isWallPe ? 'is-wall' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                    >
                      <td>
                        <BuildupBadge buildup={ce.buildup} />
                      </td>
                      <td>{ce.iv_pct != null ? fmt(ce.iv_pct, 1) : '—'}</td>
                      <td>{ce.delta != null ? Number(ce.delta).toFixed(2) : '—'}</td>
                      <td className={r.ce_itm ? 'oc-itm oc-itm--ce' : ''}>
                        {fmt(ce.ltp)}
                      </td>
                      <td className={ce.net_chg_pct >= 0 ? 'is-up' : 'is-down'}>
                        {pct(ce.net_chg_pct)}
                      </td>
                      <td>
                        <OiBar value={ce.oi} max={maxOi} side="ce" />
                      </td>
                      <td className={ce.oi_change >= 0 ? 'is-up' : 'is-down'}>
                        {fmt(ce.oi_change, 0)}
                      </td>
                      <td className="oc-ba">
                        {fmt(ce.bid)} / {fmt(ce.ask)}
                      </td>
                      <td
                        className={[
                          'oc-strike',
                          isAtm ? 'is-atm' : '',
                          isPain ? 'is-max-pain' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        {fmt(r.strike, 0)}
                        {isAtm && <small>ATM</small>}
                        {isPain && <small>MP</small>}
                      </td>
                      <td className="oc-ba">
                        {fmt(pe.bid)} / {fmt(pe.ask)}
                      </td>
                      <td className={pe.oi_change >= 0 ? 'is-up' : 'is-down'}>
                        {fmt(pe.oi_change, 0)}
                      </td>
                      <td>
                        <OiBar value={pe.oi} max={maxOi} side="pe" />
                      </td>
                      <td className={pe.net_chg_pct >= 0 ? 'is-up' : 'is-down'}>
                        {pct(pe.net_chg_pct)}
                      </td>
                      <td className={r.pe_itm ? 'oc-itm oc-itm--pe' : ''}>
                        {fmt(pe.ltp)}
                      </td>
                      <td>{pe.delta != null ? Number(pe.delta).toFixed(2) : '—'}</td>
                      <td>{pe.iv_pct != null ? fmt(pe.iv_pct, 1) : '—'}</td>
                      <td>
                        <BuildupBadge buildup={pe.buildup} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="muted option-chain__foot">
            Subscribed {data.subscribed} tokens · source {data.source} · as of {data.as_of}
            {analytics.spot_to_call_wall_pct != null && (
              <> · spot→call wall {fmt(analytics.spot_to_call_wall_pct, 3)}%</>
            )}
            {analytics.spot_to_put_wall_pct != null && (
              <> · spot→put wall {fmt(analytics.spot_to_put_wall_pct, 3)}%</>
            )}
          </p>
        </>
      )}
    </section>
  );
}
