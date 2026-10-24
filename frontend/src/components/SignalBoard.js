import React from 'react';

const SIDE_MAP = {
  LONG: 'BUY',
  SHORT: 'SELL',
  FLAT: 'HOLD',
  BUY: 'BUY',
  SELL: 'SELL',
  HOLD: 'HOLD',
};

function normalizeSide(raw) {
  const s = String(raw || 'HOLD').toUpperCase();
  return SIDE_MAP[s] || 'HOLD';
}

function sideClass(side) {
  if (side === 'BUY') return 'sig--buy';
  if (side === 'SELL') return 'sig--sell';
  return 'sig--hold';
}

function fmtPx(n, currency = true) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  const v = Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  return currency ? `₹${v}` : v;
}

/** Normalize consultant SignalCall or legacy LONG/SHORT tape into a board row. */
export function normalizeSignal(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const side = normalizeSide(raw.side);
  const targets = raw.targets || {};
  const t1 =
    targets.t1 ??
    targets.T1 ??
    raw.target ??
    raw.t1 ??
    null;
  const confidence =
    raw.confidence != null
      ? Number(raw.confidence)
      : raw.score != null
        ? Number(raw.score)
        : null;
  return {
    ...raw,
    id: raw.id || raw.symbol || raw.name,
    symbol: raw.symbol || raw.name || '—',
    name: raw.name,
    side,
    confidence:
      confidence != null && !Number.isNaN(confidence) ? confidence : null,
    thesis: raw.thesis || raw.reason || '',
    entry: raw.entry ?? raw.price ?? raw.entry_price ?? null,
    stop: raw.stop ?? raw.stop_loss ?? null,
    target: t1,
    tags: Array.isArray(raw.tags) ? raw.tags : [],
    mcx_hint: raw.mcx_hint,
    unit: raw.unit,
    change_pct: raw.change_pct,
    horizon: raw.horizon,
  };
}

function ConfidenceBar({ value }) {
  if (value == null) return null;
  const pct = Math.max(0, Math.min(100, Number(value)));
  return (
    <div className="sig-conf" title={`Confidence ${pct}`}>
      <div className="sig-conf__track">
        <div className="sig-conf__fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="sig-conf__val">{Math.round(pct)}</span>
    </div>
  );
}

/**
 * Professional BUY/SELL/HOLD signal board.
 * @param {object} props
 * @param {array} [props.signals]
 * @param {array} [props.calls] alias for signals
 * @param {string} [props.title]
 * @param {string} [props.subtitle]
 * @param {string} [props.emptyMessage]
 * @param {string} [props.source] consultant | legacy
 * @param {(symbol: string) => void} [props.onOpen]
 * @param {(sig) => void} [props.onAnalyze]
 * @param {boolean} [props.loading]
 * @param {string} [props.className]
 * @param {boolean} [props.currency] format prices as INR
 */
export default function SignalBoard({
  signals,
  calls,
  title,
  subtitle,
  emptyMessage = 'No calls on the board.',
  source,
  onOpen,
  onAnalyze,
  loading = false,
  className = '',
  currency = true,
}) {
  const rows = (signals || calls || []).map(normalizeSignal).filter(Boolean);

  return (
    <section className={`signal-board ${className}`.trim()}>
      {(title || subtitle || source) && (
        <div className="section__head signal-board__head">
          <div>
            {title ? <h3>{title}</h3> : null}
            {subtitle ? <p className="section-sub">{subtitle}</p> : null}
          </div>
          {source && (
            <span
              className={`signal-board__source ${
                source === 'consultant' ? 'is-live' : ''
              }`}
            >
              {source === 'consultant' ? 'CONSULTANT' : String(source).toUpperCase()}
            </span>
          )}
        </div>
      )}

      {loading && rows.length === 0 && (
        <p className="muted">Loading signals…</p>
      )}

      {!loading && rows.length === 0 && (
        <p className="muted signal-board__empty">{emptyMessage}</p>
      )}

      <div className="sig-grid">
        {rows.map((s, i) => (
          <article
            key={s.id || `${s.symbol}-${i}`}
            className={`sig-card ${sideClass(s.side)}`}
            style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
          >
            <header className="sig-card__head">
              <div className="sig-card__identity">
                {onOpen && s.symbol && s.symbol !== '—' ? (
                  <button
                    type="button"
                    className="sig-card__sym"
                    onClick={() =>
                      onOpen({
                        symbol: s.symbol,
                        signalContext: s.context || null,
                        side: s.side,
                        thesis: s.thesis || null,
                      })
                    }
                  >
                    {s.symbol}
                  </button>
                ) : (
                  <strong className="sig-card__sym">{s.symbol}</strong>
                )}
                {s.mcx_hint ? (
                  <p className="sig-card__hint">{s.mcx_hint}</p>
                ) : null}
              </div>
              <span
                className={`sig-card__side sig-badge sig-badge--${s.side.toLowerCase()}`}
              >
                {s.side}
              </span>
            </header>

            <ConfidenceBar value={s.confidence} />

            {s.thesis ? <p className="sig-card__thesis">{s.thesis}</p> : null}

            <div className="sig-card__levels">
              <div>
                <span>Entry</span>
                <strong>{fmtPx(s.entry, currency)}</strong>
              </div>
              <div>
                <span>Stop</span>
                <strong className="neg">{fmtPx(s.stop, currency)}</strong>
              </div>
              <div>
                <span>Target</span>
                <strong className="pos">{fmtPx(s.target, currency)}</strong>
              </div>
              <div>
                <span>
                  {s.change_pct != null
                    ? 'Day'
                    : s.horizon
                      ? 'Horizon'
                      : 'Unit'}
                </span>
                <strong
                  className={
                    s.change_pct != null
                      ? s.change_pct >= 0
                        ? 'pos'
                        : 'neg'
                      : 'mono'
                  }
                >
                  {s.change_pct != null
                    ? `${s.change_pct > 0 ? '+' : ''}${s.change_pct}%`
                    : s.horizon || s.unit || '—'}
                </strong>
              </div>
            </div>

            {s.tags.length > 0 && (
              <div className="sig-card__tags">
                {s.tags.slice(0, 6).map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
            )}

            {onAnalyze && (
              <div className="sig-card__actions">
                <button
                  type="button"
                  className="btn ghost sig-card__analyze"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAnalyze(s);
                  }}
                >
                  Analyze with LLM
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
