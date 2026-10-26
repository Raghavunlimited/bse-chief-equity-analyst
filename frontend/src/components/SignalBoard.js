import React from 'react';
import SignalAvailabilityBanner from './SignalAvailabilityBanner';

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
  const expectancy =
    raw.expectancy ||
    (raw.context && raw.context.expectancy) ||
    null;
  const badgeRaw = String(raw.badge || side || 'HOLD').toUpperCase();
  const badge =
    badgeRaw === 'STRONG_BUY' ||
    badgeRaw === 'STRONG_SELL' ||
    badgeRaw === 'BUY' ||
    badgeRaw === 'SELL' ||
    badgeRaw === 'HOLD'
      ? badgeRaw
      : side;

  const marketDataState =
    raw.data_status ||
    raw.market_data_state ||
    (raw.observation && raw.observation.market_data_state) ||
    raw.feed_status ||
    null;
  const isCurrentLive = raw.is_current_live === true;
  const isLastObs =
    raw.is_last_observation === true ||
    (raw.observation && raw.observation.is_last_observation === true) ||
    String(raw.signal_generation || '').toLowerCase() === 'halted';
  const gateResult =
    raw.gate_result ||
    (expectancy
      ? {
          code: expectancy.insufficient_history
            ? 'insufficient_history'
            : expectancy.gates && expectancy.gates.passed === false
              ? 'gate_failed'
              : expectancy.gates && expectancy.gates.passed === true
                ? 'gate_pass_research'
                : 'gate_pending',
          label: expectancy.insufficient_history
            ? 'Insufficient history — STRONG / edge blocked'
            : expectancy.gates && expectancy.gates.passed === false
              ? 'Expectancy/risk gate failed'
              : expectancy.gates && expectancy.gates.passed === true
                ? 'Gate pass (research only)'
                : 'Gate metrics pending',
          passed: expectancy.gates ? expectancy.gates.passed : null,
          insufficient_history: !!expectancy.insufficient_history,
          fail_reasons: (expectancy.gates && expectancy.gates.fail_reasons) || [],
        }
      : null);

  return {
    ...raw,
    id: raw.id || raw.symbol || raw.name,
    symbol: raw.symbol || raw.instrument || raw.name || '—',
    instrument: raw.instrument || raw.symbol || raw.name || '—',
    name: raw.name,
    desk: raw.desk || null,
    strategy: raw.strategy || null,
    side,
    badge,
    expectancy,
    gateResult,
    dataTimestamp: raw.data_timestamp || raw.as_of || null,
    marketDataState,
    isCurrentLive,
    isLastObs,
    quoteSource: raw.data_source || raw.quote_source || raw.source || null,
    quoteAgeSec: raw.quote_age_sec ?? raw.age_sec ?? null,
    timeframe: raw.timeframe || null,
    confidence:
      confidence != null && !Number.isNaN(confidence) ? confidence : null,
    thesis: raw.thesis || raw.reason || '',
    entry: raw.entry ?? raw.price ?? raw.entry_price ?? null,
    stop: raw.stop ?? raw.stop_loss ?? null,
    target: t1,
    targets: {
      t1,
      t2: targets.t2 ?? targets.T2 ?? raw.t2 ?? null,
    },
    tags: Array.isArray(raw.tags) ? raw.tags : [],
    mcx_hint:
      raw.mcx_hint ||
      (raw.context && raw.context.mcx_hint) ||
      null,
    unit: raw.unit || (raw.context && raw.context.unit) || null,
    currency: raw.currency || (raw.context && raw.context.currency) || null,
    display_label:
      raw.display_label ||
      (raw.context && raw.context.display_label) ||
      null,
    instrument_class:
      raw.instrument_class ||
      (raw.context && raw.context.instrument_class) ||
      null,
    is_mcx_listed: raw.is_mcx_listed === true,
    change_pct:
      raw.change_pct ??
      (raw.context && raw.context.change_pct) ??
      null,
    horizon: raw.horizon,
  };
}

function FeedMeta({ signal }) {
  if (!signal) return null;
  const state = String(signal.marketDataState || '').toUpperCase();
  if (!state && !signal.quoteSource) return null;
  const age =
    signal.quoteAgeSec != null && !Number.isNaN(Number(signal.quoteAgeSec))
      ? `${Number(signal.quoteAgeSec).toFixed(0)}s`
      : null;
  let label = state || 'UNKNOWN';
  if (signal.isCurrentLive) label = 'BROKER LIVE';
  else if (state === 'FALLBACK') label = 'YAHOO FALLBACK';
  else if (signal.isLastObs || state === 'STALE') label = `${state || 'STALE'} · LAST OBS`;
  return (
    <div
      className={`sig-card__feed ${
        signal.isCurrentLive
          ? 'sig-card__feed--live'
          : state === 'FALLBACK'
            ? 'sig-card__feed--fallback'
            : 'sig-card__feed--stale'
      }`}
      title="Provider / freshness — not a return claim"
    >
      <span>{label}</span>
      {signal.quoteSource ? <span>{signal.quoteSource}</span> : null}
      {signal.timeframe ? <span>{signal.timeframe}</span> : null}
      {age ? <span>age {age}</span> : null}
    </div>
  );
}

function badgeClass(badge) {
  const b = String(badge || 'HOLD').toUpperCase();
  if (b === 'STRONG_BUY') return 'sig--buy sig--strong-buy';
  if (b === 'STRONG_SELL') return 'sig--sell sig--strong-sell';
  if (b === 'BUY') return 'sig--buy';
  if (b === 'SELL') return 'sig--sell';
  return 'sig--hold';
}

function badgeLabel(badge) {
  const b = String(badge || 'HOLD').toUpperCase();
  if (b === 'STRONG_BUY') return 'STRONG BUY';
  if (b === 'STRONG_SELL') return 'STRONG SELL';
  return b;
}

/** Why a STRONG badge must not be styled as a clean pass. History and proxy win over a generic gate miss. */
function strongHold(expectancy) {
  if (!expectancy) return null;
  if (
    expectancy.insufficient_history ||
    expectancy.status_label === 'insufficient_5m_history'
  ) {
    return 'Thin history — STRONG is held';
  }
  if (expectancy.proxy) return 'Proxy data — STRONG is held';
  if (expectancy.gates && expectancy.gates.passed === false) {
    return 'Gate failed — STRONG is held';
  }
  return null;
}

function visibleTag(tag) {
  const text = String(tag);
  if (/EDGE_PROVEN/i.test(text)) return false;
  if (/^proven$/i.test(text)) return false;
  return true;
}

function fmtEdge(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toFixed(digits);
}

function GateStrip({ gateResult }) {
  if (!gateResult) return null;
  const tone =
    gateResult.code === 'gate_pass_research'
      ? 'sig-card__gate--pass'
      : gateResult.code === 'insufficient_history' || gateResult.code === 'gate_failed'
        ? 'sig-card__gate--fail'
        : '';
  const reasons = (gateResult.fail_reasons || []).slice(0, 2);
  return (
    <div className={`sig-card__gate ${tone}`.trim()}>
      <span>Gate</span>
      <strong>{gateResult.label}</strong>
      {reasons.map((reason) => (
        <strong key={reason}>{reason}</strong>
      ))}
    </div>
  );
}

function ExpectancyStrip({ expectancy, gateResult }) {
  if (!expectancy) {
    return (
      <div className="sig-card__edge" title="No walk-forward metrics yet">
        <span>Edge</span>
        <strong className="muted">pending</strong>
        <GateStrip gateResult={gateResult} />
      </div>
    );
  }
  const n = expectancy.sample_size;
  const regime = expectancy.active_regime || expectancy.regime || '—';
  const gated = expectancy.gates && expectancy.gates.passed === false;
  const insuff = expectancy.insufficient_history || expectancy.status_label === 'insufficient_5m_history';
  const tf = expectancy.data_interval || expectancy.timeframe || '';
  const titleBits = [
    `Regime ${regime}`,
    expectancy.rule_id ? `rule ${expectancy.rule_id}` : null,
    tf ? `interval ${tf}` : null,
    expectancy.strategy_version ? `v${expectancy.strategy_version}` : null,
    'Gate pass is research only',
  ].filter(Boolean);
  const researchLimit = gated || insuff || Boolean(expectancy.proxy);
  return (
    <div
      className={`sig-card__edge ${researchLimit ? 'sig-card__edge--unproven' : ''}`}
      title={titleBits.join(' · ')}
    >
      <GateStrip gateResult={gateResult} />
      {insuff ? (
        <div className="sig-card__edge-note sig-card__edge-note--block">
          <span>5m history</span>
          <strong>insufficient — STRONG blocked</strong>
        </div>
      ) : null}
      {expectancy.proxy ? (
        <div className="sig-card__edge-note sig-card__edge-note--block">
          <span>Proxy data</span>
          <strong>ungated — STRONG blocked</strong>
        </div>
      ) : null}
      {gated && !insuff ? (
        <div className="sig-card__edge-note sig-card__edge-note--block">
          <span>Expectancy gate</span>
          <strong>
            failed
            {(expectancy.gates?.fail_reasons || []).length
              ? `: ${(expectancy.gates.fail_reasons || []).slice(0, 2).join(', ')}`
              : ''}
          </strong>
        </div>
      ) : null}
      <div>
        <span>Win%</span>
        <strong>
          {expectancy.win_rate_pct != null
            ? `${fmtEdge(expectancy.win_rate_pct, 1)}%`
            : '—'}
        </strong>
      </div>
      <div>
        <span>E[R]</span>
        <strong
          className={
            expectancy.expectancy_r == null
              ? ''
              : expectancy.expectancy_r > 0
                ? 'pos'
                : 'neg'
          }
        >
          {expectancy.expectancy_r != null
            ? `${fmtEdge(expectancy.expectancy_r, 2)}R`
            : '—'}
        </strong>
      </div>
      <div>
        <span>PF</span>
        <strong>
          {expectancy.profit_factor != null
            ? fmtEdge(expectancy.profit_factor, 2)
            : '—'}
        </strong>
      </div>
      <div>
        <span>N</span>
        <strong className="mono">{n != null ? n : '—'}</strong>
      </div>
    </div>
  );
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
  availability,
  desk: deskProp,
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

      {availability ? <SignalAvailabilityBanner availability={availability} /> : null}

      {loading && rows.length === 0 && (
        <p className="muted">Loading signals…</p>
      )}

      {!loading && rows.length === 0 && !availability && (
        <p className="muted signal-board__empty">{emptyMessage}</p>
      )}
      {!loading && rows.length === 0 && availability ? (
        <p className="muted signal-board__empty">{emptyMessage}</p>
      ) : null}

      <div className="sig-grid">
        {rows.map((s, i) => {
          const hold = String(s.badge || '').toUpperCase().startsWith('STRONG_')
            ? strongHold(s.expectancy)
            : null;
          const badgeKey = String(s.badge || s.side).toLowerCase().replace(/_/g, '-');
          return (
          <article
            key={s.id || `${s.symbol}-${i}`}
            className={`sig-card ${hold ? 'sig-card--held ' : ''}${badgeClass(hold ? s.side : s.badge || s.side)}`}
            style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
            data-desk={s.desk || deskProp || undefined}
            data-strategy={s.strategy || undefined}
            data-status={s.marketDataState || undefined}
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
                        signalContext: {
                          ...(s.context || {}),
                          side: s.side,
                          badge: s.badge,
                          expectancy: s.expectancy,
                          gate_result: s.gateResult,
                          desk: s.desk || deskProp,
                          strategy: s.strategy,
                          data_status: s.marketDataState,
                          data_source: s.quoteSource,
                          data_timestamp: s.dataTimestamp,
                          thesis: s.thesis || null,
                          entry: s.entry,
                          stop: s.stop,
                          target: s.target,
                          targets: {
                            t1: s.target,
                            t2: s.targets?.t2 ?? s.t2 ?? null,
                          },
                          price: s.entry ?? s.price,
                        },
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
                <p className="sig-card__meta-line muted">
                  {[s.desk || deskProp, s.strategy, s.marketDataState]
                    .filter(Boolean)
                    .join(' · ')}
                  {s.dataTimestamp
                    ? ` · ${String(s.dataTimestamp).slice(0, 16)}`
                    : ''}
                </p>
                {s.display_label ? (
                  <p className="sig-card__hint sig-card__hint--proxy">
                    {s.display_label}
                    {s.currency ? ` · ${s.currency}` : ''}
                    {s.unit ? ` · ${s.unit}` : ''}
                  </p>
                ) : null}
                {s.mcx_hint ? (
                  <p className="sig-card__hint">{s.mcx_hint}</p>
                ) : null}
              </div>
              <span
                className={`sig-card__side sig-badge ${
                  hold ? 'sig-badge--held' : `sig-badge--${badgeKey}`
                }`}
              >
                {badgeLabel(s.badge || s.side)}
              </span>
            </header>
            {hold ? <p className="sig-card__hold">{hold}</p> : null}

            <ConfidenceBar value={s.confidence} />
            <FeedMeta signal={s} />

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

            <ExpectancyStrip expectancy={s.expectancy} gateResult={s.gateResult} />

            {s.tags.filter(visibleTag).length > 0 && (
              <div className="sig-card__tags">
                {s.tags.filter(visibleTag).slice(0, 6).map((t) => (
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
          );
        })}
      </div>
    </section>
  );
}
