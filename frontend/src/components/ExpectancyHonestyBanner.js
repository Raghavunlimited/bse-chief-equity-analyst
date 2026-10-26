import React from 'react';

/**
 * Desk-level prominence for Index / Intraday expectancy honesty.
 * Does not create signals — surfaces proxy / thin 5m history / gate fails.
 */
export default function ExpectancyHonestyBanner({ honesty, desk }) {
  if (!honesty || !honesty.prominent) return null;
  const d = String(desk || '').toLowerCase();
  if (d && d !== 'intraday' && d !== 'index') return null;

  return (
    <div
      className="banner warn expectancy-honesty"
      role="status"
      data-testid="expectancy-honesty"
      data-desk={d || undefined}
    >
      <strong>{honesty.label || 'Expectancy honesty'}</strong>
      {honesty.detail ? <p>{honesty.detail}</p> : null}
      <ul className="expectancy-honesty__counts">
        {honesty.insufficient_history_count > 0 ? (
          <li>
            Insufficient 5m history: {honesty.insufficient_history_count} — STRONG
            blocked
          </li>
        ) : null}
        {honesty.proxy_count > 0 ? (
          <li>Proxy / ungated metrics: {honesty.proxy_count} — STRONG blocked</li>
        ) : null}
        {honesty.gate_failed_count > 0 ? (
          <li>
            Expectancy/risk gate failed: {honesty.gate_failed_count}
            {(honesty.fail_reasons || []).length
              ? ` (${(honesty.fail_reasons || []).slice(0, 3).join(', ')})`
              : ''}
          </li>
        ) : null}
      </ul>
      <p className="muted expectancy-honesty__boundary">
        {honesty.boundary ||
          'Research only — gate pass ≠ proven edge. Stale data never creates a fresh signal.'}
      </p>
    </div>
  );
}
