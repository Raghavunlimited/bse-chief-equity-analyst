import React, { useMemo } from 'react';

function fmt(n, d = 0) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
}

/**
 * Call vs Put OI across strikes (and expiry availability table).
 * Renders only values present on the oi-viz payload — never invents bars.
 */
export default function OiComparisonChart({ viz }) {
  const maxOi = useMemo(() => {
    if (!viz?.available) return 1;
    let m = 1;
    (viz.call_oi_by_strike || []).forEach((p) => {
      if (p.oi != null) m = Math.max(m, Number(p.oi));
    });
    (viz.put_oi_by_strike || []).forEach((p) => {
      if (p.oi != null) m = Math.max(m, Number(p.oi));
    });
    return m;
  }, [viz]);

  if (!viz) {
    return (
      <p className="muted" data-testid="oi-viz-loading" role="status">
        Loading OI visualization…
      </p>
    );
  }

  if (!viz.available) {
    return (
      <div className="oi-viz oi-viz--unavailable" data-testid="oi-viz-unavailable" role="status">
        <div className="banner warn">
          <strong>OI visualization unavailable</strong>
          <p>{viz.blocker || viz.reason || 'Option chain inactive'}</p>
          <p className="muted">
            Provider: {viz.provider || 'kotak_neo_ws'} · e2e verified in CI:{' '}
            {viz.provider_e2e_verified_in_ci ? 'yes' : 'no'}
          </p>
        </div>
        {viz.expiries_oi_comparison?.length > 0 && (
          <div className="oi-viz__expiries">
            <h5>Listed expiries (catalog — OI not loaded)</h5>
            <ul>
              {viz.expiries_oi_comparison.slice(0, 8).map((e) => (
                <li key={e.expiry}>
                  {e.expiry}: <em>OI unavailable</em>
                  {e.reason ? ` — ${e.reason}` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="muted oi-viz__disclaimer" data-testid="oi-viz-disclaimer">
          {viz.signal_disclaimer}
        </p>
      </div>
    );
  }

  const rows = viz.series || [];
  const fresh = viz.freshness || {};

  return (
    <div className="oi-viz" data-testid="oi-viz" data-status={viz.status}>
      <div className="oi-viz__head">
        <h5>
          Call vs Put OI · {viz.underlying} · {viz.active_expiry}
        </h5>
        <span
          className={`live-pill chart-ws__status ${
            fresh.status === 'stale' || fresh.status === 'unavailable'
              ? 'is-stale'
              : fresh.status === 'aging'
                ? 'is-aging'
                : 'is-ok'
          }`}
          role="status"
          data-testid="oi-viz-freshness"
        >
          {fresh.label || viz.status}
        </span>
        <span className="muted">src {viz.source}</span>
        {viz.underlying_price?.available && (
          <span>
            Underlying <strong>{fmt(viz.underlying_price.value, 2)}</strong>
          </span>
        )}
        {!viz.underlying_price?.available && (
          <span className="muted">Underlying price unavailable</span>
        )}
      </div>

      {(fresh.status === 'stale' || fresh.status === 'aging') && (
        <p className="banner warn" role="status">
          Quote ages {fresh.label}
          {fresh.max_age_sec != null ? ` (max ${fmt(fresh.max_age_sec, 0)}s)` : ''}.
          OI may be delayed — not treated as a trade signal.
        </p>
      )}

      <div className="oi-viz__legend" aria-hidden="true">
        <span className="oi-viz__swatch oi-viz__swatch--ce">Call OI</span>
        <span className="oi-viz__swatch oi-viz__swatch--pe">Put OI</span>
      </div>

      <div className="oi-viz__bars" role="img" aria-label="Call and put open interest by strike">
        {rows.map((r) => {
          const cOi = r.call?.oi?.value;
          const pOi = r.put?.oi?.value;
          const cPct = cOi != null ? Math.min(100, (Number(cOi) / maxOi) * 100) : 0;
          const pPct = pOi != null ? Math.min(100, (Number(pOi) / maxOi) * 100) : 0;
          return (
            <div
              key={r.strike}
              className={`oi-viz__row ${r.atm ? 'is-atm' : ''}`}
              data-strike={r.strike}
            >
              <div className="oi-viz__ce">
                {r.call?.oi?.available ? (
                  <div className="oi-viz__bar oi-viz__bar--ce" style={{ width: `${cPct}%` }}>
                    <span>{fmt(cOi)}</span>
                  </div>
                ) : (
                  <span className="oi-viz__missing" title={r.call?.oi?.reason || 'missing'}>
                    n/a
                  </span>
                )}
              </div>
              <div className="oi-viz__strike">
                {fmt(r.strike)}
                {r.atm ? <small>ATM</small> : null}
              </div>
              <div className="oi-viz__pe">
                {r.put?.oi?.available ? (
                  <div className="oi-viz__bar oi-viz__bar--pe" style={{ width: `${pPct}%` }}>
                    <span>{fmt(pOi)}</span>
                  </div>
                ) : (
                  <span className="oi-viz__missing" title={r.put?.oi?.reason || 'missing'}>
                    n/a
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="oi-viz__totals">
        <span>
          Call OI Σ{' '}
          <strong>
            {viz.totals?.call_oi_available ? fmt(viz.totals.call_oi) : 'unavailable'}
          </strong>
        </span>
        <span>
          Put OI Σ{' '}
          <strong>
            {viz.totals?.put_oi_available ? fmt(viz.totals.put_oi) : 'unavailable'}
          </strong>
        </span>
        <span title={viz.totals?.pcr_note || ''}>
          PCR{' '}
          <strong>
            {viz.totals?.pcr != null ? Number(viz.totals.pcr).toFixed(3) : 'unavailable'}
          </strong>
        </span>
      </div>

      <div className="oi-viz__expiries">
        <h5>OI by expiry</h5>
        <p className="muted">
          Only the activated expiry has live OI. Other listed dates stay unavailable
          (not zero).
        </p>
        <table className="oi-viz__exp-table">
          <thead>
            <tr>
              <th>Expiry</th>
              <th>Active</th>
              <th>Call OI Σ</th>
              <th>Put OI Σ</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(viz.expiries_oi_comparison || []).slice(0, 10).map((e) => (
              <tr key={e.expiry} className={e.active ? 'is-active' : ''}>
                <td>{e.expiry}</td>
                <td>{e.active ? 'yes' : '—'}</td>
                <td>{e.oi_available ? fmt(e.call_oi_total) : '—'}</td>
                <td>{e.oi_available ? fmt(e.put_oi_total) : '—'}</td>
                <td>{e.oi_available ? 'OK' : e.reason || 'unavailable'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="muted oi-viz__disclaimer" data-testid="oi-viz-disclaimer">
        {viz.signal_disclaimer}
        {viz.field_semantics?.iv
          ? ` · IV semantic: ${viz.field_semantics.iv}`
          : ''}
        {viz.field_semantics?.oi_change
          ? ` · ΔOI semantic: ${viz.field_semantics.oi_change}`
          : ''}
      </p>
    </div>
  );
}
