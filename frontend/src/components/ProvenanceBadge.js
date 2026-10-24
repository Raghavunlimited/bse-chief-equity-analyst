import React from 'react';

const LABELS = {
  demo: { text: 'DEMO DATA', className: 'prov-badge prov-badge--demo' },
  live: { text: 'LIVE', className: 'prov-badge prov-badge--live' },
  delayed: { text: 'DELAYED', className: 'prov-badge prov-badge--delayed' },
  stale: { text: 'STALE', className: 'prov-badge prov-badge--stale' },
};

/**
 * Prominent data-mode badge — never imply demo is live.
 */
export default function ProvenanceBadge({ dataMode, note, compact }) {
  const mode = (dataMode || 'demo').toLowerCase();
  const meta = LABELS[mode] || LABELS.demo;
  return (
    <span
      className={meta.className}
      title={note || meta.text}
      role="status"
      aria-label={`Data provenance: ${meta.text}`}
    >
      {meta.text}
      {!compact && note ? <span className="prov-badge__note"> · {note}</span> : null}
    </span>
  );
}
