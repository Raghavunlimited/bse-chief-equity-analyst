import React from 'react';

const TONE = {
  qualifying: 'ok',
  no_qualifying: 'info',
  data_blocked: 'warn',
  gate_blocked: 'warn',
  ledger_empty: 'info',
  ledger_demo_filtered: 'info',
  ledger_has_published: 'ok',
};

/**
 * Honest empty / blocked / qualifying state for consultant boards and ledger.
 * Never implies execution or guaranteed returns.
 */
export default function SignalAvailabilityBanner({ availability, className = '' }) {
  if (!availability || !availability.code) return null;
  const tone = TONE[availability.code] || 'info';
  return (
    <div
      className={`banner signal-availability banner--${tone} ${className}`.trim()}
      role="status"
      data-availability={availability.code}
    >
      <strong>{availability.label || availability.code}</strong>
      {availability.detail ? <p>{availability.detail}</p> : null}
      <p className="muted signal-availability__boundary">
        {availability.boundary ||
          'Research only — not an order instruction and not a return guarantee.'}
      </p>
    </div>
  );
}
