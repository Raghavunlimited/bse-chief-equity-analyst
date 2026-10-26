import React from 'react';

const LABELS = {
  live: { text: 'BROKER LIVE', className: 'prov-badge prov-badge--live' },
  fallback: { text: 'YAHOO FALLBACK', className: 'prov-badge prov-badge--fallback' },
  delayed: { text: 'DELAYED', className: 'prov-badge prov-badge--delayed' },
  stale: { text: 'STALE · LAST OBS', className: 'prov-badge prov-badge--stale' },
  eod: { text: 'EOD CLOSE', className: 'prov-badge prov-badge--delayed' },
  eod_close: { text: 'EOD CLOSE', className: 'prov-badge prov-badge--delayed' },
  unavailable: { text: 'UNAVAILABLE', className: 'prov-badge prov-badge--stale' },
  error: { text: 'FEED ERROR', className: 'prov-badge prov-badge--stale' },
  ltp: { text: 'LTP', className: 'prov-badge prov-badge--delayed' },
};

/**
 * Data-mode badge — never maps Yahoo/research to BROKER LIVE.
 */
export default function ProvenanceBadge({ dataMode, note, priceKind, marketDataState }) {
  const state = String(marketDataState || '').toUpperCase();
  let mode = (dataMode || priceKind || 'delayed').toLowerCase();
  if (state === 'LIVE') mode = 'live';
  else if (state === 'FALLBACK') mode = 'fallback';
  else if (state === 'STALE') mode = 'stale';
  else if (state === 'EOD') mode = 'eod';
  else if (state === 'UNAVAILABLE' || state === 'ERROR') mode = 'unavailable';
  else if (
    state === 'POST_MARKET' ||
    state === 'PRE_MARKET' ||
    state === 'WEEKEND' ||
    state === 'HOLIDAY' ||
    state === 'DELAYED'
  ) {
    mode = 'delayed';
  }
  // Hard rule: never show BROKER LIVE for fallback provenance
  if (mode === 'live' && String(dataMode || '').toLowerCase() === 'fallback') {
    mode = 'fallback';
  }
  const meta = LABELS[mode] || LABELS.delayed;
  return (
    <span className={meta.className} title={note || meta.text}>
      {meta.text}
      {note ? <span className="prov-badge__note"> · {note}</span> : null}
    </span>
  );
}
