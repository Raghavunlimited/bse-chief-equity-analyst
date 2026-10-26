/**
 * Back-compat shim — Phase 4 replaced Recharts candles with ChartWorkstation.
 * Prefer importing ChartWorkstation directly.
 */
import React from 'react';
import ChartWorkstation from './ChartWorkstation';

export default function ProStockChart({
  symbol,
  signalContext = null,
  bars: _bars,
  rangeDays: _rangeDays,
  onRangeChange: _onRangeChange,
  loading: _loading,
  defaultInterval = '1d',
}) {
  if (!symbol) {
    return (
      <p className="muted">
        Open a symbol to load the Lightweight Charts workstation (1m–1D).
      </p>
    );
  }
  return (
    <ChartWorkstation
      symbol={symbol}
      signalContext={signalContext}
      defaultInterval={defaultInterval}
    />
  );
}
