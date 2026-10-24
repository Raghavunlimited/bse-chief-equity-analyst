import React, { useEffect, useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { deskAPI } from '../services/api';
import LlmAnalyzePanel from './LlmAnalyzePanel';

function fmt(n, d = 1) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
}

function pct(n, d = 1) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `${fmt(n, d)}%`;
}

function hasSignalContext(ctx) {
  if (!ctx || typeof ctx !== 'object') return false;
  return Boolean(
    ctx.fundamentals ||
      ctx.volume ||
      ctx.oi ||
      ctx.oi_note ||
      ctx.side ||
      ctx.thesis ||
      ctx.confidence != null
  );
}

/**
 * @param {object} props
 * @param {string} props.symbol
 * @param {() => void} props.onClose
 * @param {object} [props.signalContext] enrichment / call context from consultant board
 */
export default function StockModal({ symbol, onClose, signalContext }) {
  const [detail, setDetail] = useState(null);
  const [bars, setBars] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetail(null);
    setBars([]);
    (async () => {
      try {
        const [d, c] = await Promise.all([
          deskAPI.getStock(symbol),
          deskAPI.getChart(symbol, 90).catch(() => ({ data: { bars: [] } })),
        ]);
        if (cancelled) return;
        setDetail(d.data);
        setBars(c.data?.bars || []);
      } catch (e) {
        if (!cancelled) {
          setError(e.response?.data?.detail || e.message || 'Failed to load');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const llmSignal = useMemo(() => {
    if (!symbol || !detail) return null;
    return {
      symbol,
      sector: detail.sector,
      latest: detail.latest,
      indicators: detail.indicators,
      has_eod: detail.has_eod,
      fundamentals: detail.fundamentals
        ? {
            pe_ttm: detail.fundamentals.pe_ttm,
            pb: detail.fundamentals.pb,
            roe_pct: detail.fundamentals.roe_pct,
            market_cap_cr: detail.fundamentals.market_cap_cr,
            recommendation: detail.fundamentals.recommendation,
          }
        : null,
      signal_context: signalContext || null,
    };
  }, [symbol, detail, signalContext]);

  if (!symbol) return null;
  const f = detail?.fundamentals;
  const price =
    detail?.latest?.close ??
    f?.live_price ??
    null;

  const fundRows = [
    { label: 'Market cap', value: f?.market_cap_cr != null ? `₹${fmt(f.market_cap_cr, 0)} Cr` : null },
    { label: 'PE (TTM)', value: f?.pe_ttm != null ? fmt(f.pe_ttm) : null },
    { label: 'PB', value: f?.pb != null ? fmt(f.pb) : null },
    { label: 'Book value', value: f?.book_value != null ? `₹${fmt(f.book_value, 0)}` : null },
    { label: 'EPS', value: f?.eps_ttm != null ? fmt(f.eps_ttm) : null },
    { label: 'ROE', value: f?.roe_pct != null ? pct(f.roe_pct) : null },
    { label: 'ROCE', value: f?.roce_pct != null ? pct(f.roce_pct) : null },
    {
      label: 'Div yield',
      value: f?.dividend_yield_pct != null ? pct(f.dividend_yield_pct, 2) : null,
    },
    {
      label: 'Profit margin',
      value: f?.profit_margin_pct != null ? pct(f.profit_margin_pct) : null,
    },
    {
      label: 'Rev growth',
      value: f?.revenue_growth != null ? pct(f.revenue_growth * 100) : null,
    },
    { label: 'D/E', value: f?.debt_to_equity != null ? fmt(f.debt_to_equity) : null },
    { label: 'Face value', value: f?.face_value != null ? `₹${fmt(f.face_value, 0)}` : null },
    {
      label: '52W high',
      value: f?.fifty_two_week_high != null ? `₹${fmt(f.fifty_two_week_high, 0)}` : null,
    },
    {
      label: '52W low',
      value: f?.fifty_two_week_low != null ? `₹${fmt(f.fifty_two_week_low, 0)}` : null,
    },
  ].filter((r) => r.value != null);

  const showCtx = hasSignalContext(signalContext);
  const ctxFund = signalContext?.fundamentals;
  const ctxVol = signalContext?.volume;
  const ctxOi = signalContext?.oi;
  const oiNote = signalContext?.oi_note || ctxOi?.oi_note;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="modal__head">
          <div>
            <h2>{symbol}</h2>
            {detail && (
              <p>
                {detail.sector}
                {f?.name ? ` · ${f.name}` : ''}
                {f?.source ? ` · ${f.source}` : ''}
                {f?.cached ? ' · cached' : ''}
              </p>
            )}
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            Close
          </button>
        </header>

        {error && <p className="error-text">{error}</p>}
        {loading && <p className="muted">Loading price &amp; financials…</p>}

        {detail && (
          <>
            <div className="modal__stats">
              <div>
                <span>Price</span>
                <strong>{price != null ? `₹${fmt(price, 2)}` : '—'}</strong>
              </div>
              <div>
                <span>RSI</span>
                <strong>{detail.indicators?.rsi_14?.toFixed?.(1) ?? '—'}</strong>
              </div>
              <div>
                <span>ROC 3d</span>
                <strong>
                  {detail.indicators?.roc_3 != null
                    ? `${detail.indicators.roc_3.toFixed(2)}%`
                    : '—'}
                </strong>
              </div>
              <div>
                <span>As of</span>
                <strong>{detail.latest?.trade_date || (f?.available ? 'Live ratios' : '—')}</strong>
              </div>
            </div>

            {!detail.has_eod && (
              <p className="muted modal-note">
                No local EOD candles yet — financials still load from Screener. Run Force full to
                add this name to the swing scan universe.
              </p>
            )}

            {showCtx && (
              <div className="modal__signal-context">
                <h4>Signal context</h4>
                {(signalContext.side || signalContext.confidence != null) && (
                  <p className="modal__signal-context__call">
                    {signalContext.side ? (
                      <span className={`sig-badge sig-badge--${String(signalContext.side).toLowerCase()}`}>
                        {signalContext.side}
                      </span>
                    ) : null}
                    {signalContext.confidence != null
                      ? ` · confidence ${fmt(signalContext.confidence, 0)}`
                      : ''}
                    {signalContext.desk ? ` · ${signalContext.desk}` : ''}
                  </p>
                )}
                {signalContext.thesis ? (
                  <p className="modal__signal-context__thesis">{signalContext.thesis}</p>
                ) : null}

                <div className="stat-grid compact">
                  {ctxVol?.available && (
                    <>
                      <div>
                        <span>EOD volume</span>
                        <strong>
                          {ctxVol.volume != null ? fmt(ctxVol.volume, 0) : '—'}
                        </strong>
                      </div>
                      <div>
                        <span>Vol MA20</span>
                        <strong>
                          {ctxVol.vol_ma_20 != null ? fmt(ctxVol.vol_ma_20, 0) : '—'}
                        </strong>
                      </div>
                      <div>
                        <span>Vol vs MA20</span>
                        <strong>
                          {ctxVol.vol_vs_ma20 != null
                            ? `${fmt(ctxVol.vol_vs_ma20, 2)}×`
                            : '—'}
                        </strong>
                      </div>
                    </>
                  )}
                  {ctxFund?.available && (
                    <>
                      <div>
                        <span>MCap (signal)</span>
                        <strong>
                          {ctxFund.market_cap_cr != null
                            ? `₹${fmt(ctxFund.market_cap_cr, 0)} Cr`
                            : '—'}
                        </strong>
                      </div>
                      <div>
                        <span>PE (signal)</span>
                        <strong>
                          {ctxFund.pe_ttm != null ? fmt(ctxFund.pe_ttm) : '—'}
                        </strong>
                      </div>
                      <div>
                        <span>ROE (signal)</span>
                        <strong>
                          {ctxFund.roe_pct != null ? pct(ctxFund.roe_pct) : '—'}
                        </strong>
                      </div>
                    </>
                  )}
                  <div>
                    <span>Open interest</span>
                    <strong className="muted">
                      {ctxOi?.available ? fmt(ctxOi.oi, 0) : 'Unavailable'}
                    </strong>
                  </div>
                </div>

                {ctxVol?.note && !ctxVol.available && (
                  <p className="muted modal-note">{ctxVol.note}</p>
                )}
                {ctxVol?.available && ctxVol.note && (
                  <p className="muted modal-note">{ctxVol.note}</p>
                )}
                {oiNote && (
                  <p className="muted modal-note modal__oi-note">{oiNote}</p>
                )}
              </div>
            )}

            <div className="modal__fundamentals">
              <h4>Financials</h4>
              <p className="muted modal__fundamentals-lead">
                Screener / quote ratios for this name (cached when fresh). Independent of the
                signal tape.
              </p>
              {f?.available && fundRows.length > 0 ? (
                <div className="stat-grid compact">
                  {fundRows.map((r) => (
                    <div key={r.label}>
                      <span>{r.label}</span>
                      <strong>{r.value}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">
                  {f?.message || 'Financials unavailable right now. Try again in a minute.'}
                </p>
              )}
              {f?.recommendation && (
                <p className="muted fund-rec">
                  Street lean: {f.recommendation}
                  {f.target_mean != null ? ` · mean target ₹${fmt(f.target_mean, 0)}` : ''}
                </p>
              )}
            </div>

            {bars.length > 0 ? (
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={bars}>
                    <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#8B93A7', fontSize: 10 }}
                      tickFormatter={(v) => v.slice(5)}
                      minTickGap={40}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tick={{ fill: '#8B93A7', fontSize: 10 }}
                      width={56}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#141A22',
                        border: '1px solid #2A3340',
                        borderRadius: 8,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="close"
                      stroke="#E8A838"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              !loading && (
                <p className="muted modal-note">Chart appears after this symbol is ingested.</p>
              )
            )}

            {llmSignal && (
              <LlmAnalyzePanel
                signal={llmSignal}
                context={{
                  source: 'stock_modal',
                  bars: bars.slice(-5),
                  signal_context: signalContext || undefined,
                }}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
