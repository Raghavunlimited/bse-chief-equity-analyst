import React from 'react';

function fmt(n, digits = 1) {
  if (n == null || Number.isNaN(n)) return '—';
  return Number(n).toLocaleString('en-IN', {
    maximumFractionDigits: digits,
  });
}

export default function PickCard({
  pick,
  index,
  onOpen,
  onLogTrade,
  goalHint,
}) {
  if (!pick) return null;
  const {
    entry_price: entry,
    stop_loss: stop,
    targets,
    risk_pct,
    reward_pct,
    risk_reward,
    position_value,
    shares,
    risk_rs,
    fundamentals: f,
  } = pick;
  const hasSizing =
    position_value != null || shares != null || risk_rs != null;

  const potentialRs =
    goalHint?.potential_reward_rs ??
    (risk_rs != null && risk_reward != null
      ? Number(risk_rs) * Number(risk_reward)
      : null);

  return (
    <article
      className="pick-card"
      style={{ animationDelay: `${0.12 + index * 0.1}s` }}
      onClick={() => onOpen?.(pick.symbol)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onOpen?.(pick.symbol)}
    >
      <header className="pick-card__head">
        <div>
          <h2 className="pick-card__symbol">{pick.symbol}</h2>
          <p className="pick-card__sector">{pick.sector}</p>
        </div>
        <div className="pick-card__score" title="Setup score / 100">
          {pick.score}
        </div>
      </header>

      <p className="pick-card__thesis">{pick.thesis}</p>

      <div className="pick-card__levels">
        <div>
          <span>Entry</span>
          <strong>₹{entry?.toLocaleString('en-IN')}</strong>
        </div>
        <div>
          <span>Stop</span>
          <strong className="neg">₹{stop?.toLocaleString('en-IN')}</strong>
        </div>
        <div>
          <span>T1</span>
          <strong className="pos">₹{targets?.t1?.toLocaleString('en-IN')}</strong>
        </div>
        <div>
          <span>T2</span>
          <strong className="pos">₹{targets?.t2?.toLocaleString('en-IN')}</strong>
        </div>
      </div>

      {f?.available && (
        <div className="pick-card__fundamentals">
          {f.live_price != null && (
            <div>
              <span>Live</span>
              <strong>₹{fmt(f.live_price, 2)}</strong>
            </div>
          )}
          <div>
            <span>MCap</span>
            <strong>{f.market_cap_cr != null ? `₹${fmt(f.market_cap_cr, 0)} Cr` : '—'}</strong>
          </div>
          <div>
            <span>PE</span>
            <strong>{fmt(f.pe_ttm)}</strong>
          </div>
          <div>
            <span>ROE</span>
            <strong>
              {f.roe_pct != null ? `${fmt(f.roe_pct)}%` : '—'}
            </strong>
          </div>
        </div>
      )}

      {hasSizing && (
        <div className="pick-card__sizing">
          <div>
            <span>Shares</span>
            <strong>{fmt(shares ?? pick.position_size, 0)}</strong>
          </div>
          <div>
            <span>Value</span>
            <strong>
              {position_value != null ? `₹${fmt(position_value, 0)}` : '—'}
            </strong>
          </div>
          <div>
            <span>Risk ₹</span>
            <strong className="neg">
              {risk_rs != null ? `₹${fmt(risk_rs, 0)}` : '—'}
            </strong>
          </div>
          <div>
            <span>Book</span>
            <strong>{pick.portfolio_pct != null ? `${pick.portfolio_pct}%` : '—'}</strong>
          </div>
        </div>
      )}

      {potentialRs != null && potentialRs > 0 && (
        <p className="pick-card__goal-hint">
          Goal contribution ~₹{fmt(potentialRs, 0)} at planned R:R
          {goalHint?.risk_reward != null ? ` (${goalHint.risk_reward})` : ''}
        </p>
      )}

      <footer className="pick-card__meta">
        <span>Risk {risk_pct}%</span>
        <span>Reward {reward_pct}%</span>
        <span>R:R {risk_reward}</span>
        {pick.entry_style ? <span>{pick.entry_style}</span> : null}
        {onLogTrade && (
          <button
            type="button"
            className="pick-card__log"
            onClick={(e) => {
              e.stopPropagation();
              onLogTrade(pick.symbol);
            }}
          >
            Log trade
          </button>
        )}
      </footer>
    </article>
  );
}
