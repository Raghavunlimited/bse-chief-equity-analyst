import React, { useCallback, useEffect, useRef, useState } from 'react';
import { deskAPI } from '../services/api';
import ExpectancyHonestyBanner from './ExpectancyHonestyBanner';
import SignalBoard from './SignalBoard';
import OptionChainPanel from './OptionChainPanel';

export default function IndexDesk({ onOpen, onAnalyze }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await deskAPI.getIndexDesk();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Index feed failed');
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
    const sec = Math.max(12, data?.poll_seconds || 20) * 1000;
    timer.current = setInterval(load, sec);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [live, load, data?.poll_seconds]);

  const signals = data?.signals || data?.calls || [];
  const session = data?.session || {};
  const rel = data?.relative_bn_vs_nifty_pct;
  const nifty = signals.find((s) => String(s.symbol).toUpperCase() === 'NIFTY');
  const bn = signals.find((s) => String(s.symbol).toUpperCase() === 'BANKNIFTY');

  return (
    <section className="section live-desk" id="section-index">
      <div className="section__head">
        <div>
          <h3>Index tape — Nifty · BankNifty</h3>
          <p className="section-sub">
            Multi-timeframe bias: daily SMA regime + 5m EMA stack + VWAP + RSI.
            Live PCR / Call·Put walls adjust confidence when Kotak chain is active.
            Research only — not a holy grail.
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

      {(nifty || bn) && (
        <div className="index-desk__strip">
          {nifty && (
            <div className="index-desk__tile">
              <span>Nifty 50</span>
              <strong>
                {nifty.price != null
                  ? Number(nifty.price).toLocaleString('en-IN', { maximumFractionDigits: 2 })
                  : nifty.entry != null
                    ? Number(nifty.entry).toLocaleString('en-IN', { maximumFractionDigits: 2 })
                    : '—'}
              </strong>
              <em className={`sig-badge sig-badge--${String(nifty.side || 'hold').toLowerCase()}`}>
                {nifty.side}
              </em>
              {nifty.change_pct != null && (
                <small className={nifty.change_pct >= 0 ? 'is-up' : 'is-down'}>
                  {nifty.change_pct >= 0 ? '+' : ''}
                  {Number(nifty.change_pct).toFixed(2)}%
                </small>
              )}
            </div>
          )}
          {bn && (
            <div className="index-desk__tile">
              <span>Bank Nifty</span>
              <strong>
                {bn.price != null
                  ? Number(bn.price).toLocaleString('en-IN', { maximumFractionDigits: 2 })
                  : bn.entry != null
                    ? Number(bn.entry).toLocaleString('en-IN', { maximumFractionDigits: 2 })
                    : '—'}
              </strong>
              <em className={`sig-badge sig-badge--${String(bn.side || 'hold').toLowerCase()}`}>
                {bn.side}
              </em>
              {bn.change_pct != null && (
                <small className={bn.change_pct >= 0 ? 'is-up' : 'is-down'}>
                  {bn.change_pct >= 0 ? '+' : ''}
                  {Number(bn.change_pct).toFixed(2)}%
                </small>
              )}
            </div>
          )}
          {rel != null && (
            <div className="index-desk__tile index-desk__tile--rel">
              <span>BN vs Nifty (day)</span>
              <strong className={rel >= 0 ? 'is-up' : 'is-down'}>
                {rel >= 0 ? '+' : ''}
                {Number(rel).toFixed(2)}%
              </strong>
            </div>
          )}
        </div>
      )}

      {data?.strategy_notes && (
        <p className="muted index-desk__notes">
          Strategy <code>{data.strategy || 'index_mtf_vwap_v1'}</code> — {data.strategy_notes}
        </p>
      )}

      {data?.feed_health && (
        <div
          className={`banner ${
            data.feed_health.broker_live
              ? 'ok'
              : data.live_calls_allowed
                ? 'info'
                : 'warn'
          }`}
          role="status"
        >
          <strong>
            {data.feed_health.market_data_state ||
              data.feed_health.feed_status ||
              'FEED'}
            {data.feed_health.broker_live ? ' · BROKER' : ' · RESEARCH'}
          </strong>
          <p>{data.feed_health.message || data.message}</p>
        </div>
      )}
      {error && <p className="error-text">{error}</p>}
      {loading && !data && <p className="muted">Loading index LTP bias…</p>}

      <ExpectancyHonestyBanner desk="index" honesty={data?.expectancy_honesty} />

      {(signals.length > 0 || data?.signal_availability) && (
        <SignalBoard
          signals={signals}
          desk="index"
          availability={data?.signal_availability}
          onOpen={onOpen}
          onAnalyze={onAnalyze}
          emptyMessage="No index calls on the board."
        />
      )}

      {(signals.find((s) => s.option_chain?.available) || data?.option_chains) && (
        <div className="index-desk__chain-hints">
          {signals
            .filter((s) => s.option_chain?.available)
            .map((s) => {
              const a = s.option_chain?.analytics || {};
              return (
                <div key={s.symbol} className="index-desk__chain-hint">
                  <strong>{s.symbol}</strong>
                  <span>PCR {a.total_oi_pcr ?? '—'}</span>
                  <span>{a.pcr_regime || '—'}</span>
                  <span>CW {a.call_wall ?? '—'}</span>
                  <span>PW {a.put_wall ?? '—'}</span>
                  <span>MP {a.max_pain ?? '—'}</span>
                </div>
              );
            })}
        </div>
      )}

      <OptionChainPanel defaultUnderlying="NIFTY" />
    </section>
  );
}
