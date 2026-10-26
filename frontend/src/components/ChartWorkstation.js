import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createChart, CrosshairMode } from 'lightweight-charts';
import { deskAPI } from '../services/api';

const INTERVALS = [
  { id: '1m', label: '1m' },
  { id: '5m', label: '5m' },
  { id: '15m', label: '15m' },
  { id: '1h', label: '1H' },
  { id: '1d', label: '1D' },
];

const IND_OPTIONS = [
  { id: 'rsi', label: 'RSI' },
  { id: 'macd', label: 'MACD' },
  { id: 'oi', label: 'OI' },
];

const CHART_OPTS = {
  layout: {
    background: { color: 'transparent' },
    textColor: 'rgba(230, 232, 238, 0.72)',
    fontSize: 11,
  },
  grid: {
    vertLines: { color: 'rgba(255,255,255,0.04)' },
    horzLines: { color: 'rgba(255,255,255,0.04)' },
  },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
  timeScale: {
    borderColor: 'rgba(255,255,255,0.08)',
    timeVisible: true,
    secondsVisible: false,
  },
};

function fmt(n, d = 2) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
}

function extractCallLevels(signalContext) {
  if (!signalContext || typeof signalContext !== 'object') return null;
  const targets = signalContext.targets || {};
  const entry =
    signalContext.entry ??
    signalContext.entry_price ??
    signalContext.price ??
    null;
  const stop = signalContext.stop ?? signalContext.stop_loss ?? null;
  const t1 =
    targets.t1 ?? targets.T1 ?? signalContext.target ?? signalContext.t1 ?? null;
  const t2 = targets.t2 ?? targets.T2 ?? signalContext.t2 ?? null;
  if (entry == null && stop == null && t1 == null) return null;
  return {
    entry: entry != null ? Number(entry) : null,
    stop: stop != null ? Number(stop) : null,
    t1: t1 != null ? Number(t1) : null,
    t2: t2 != null ? Number(t2) : null,
    side: String(signalContext.side || signalContext.direction || '').toUpperCase(),
  };
}

function riskReward(levels, ltp) {
  if (!levels || ltp == null) return null;
  const { entry, stop, t1, t2, side } = levels;
  if (entry == null || stop == null || entry === stop) return null;
  const risk = Math.abs(entry - stop);
  if (risk < 1e-9) return null;
  const isSell = side === 'SELL' || side === 'SHORT';
  const rewardTo = (target) => {
    if (target == null) return null;
    const reward = isSell ? entry - target : target - entry;
    return reward / risk;
  };
  const liveR = isSell ? (entry - ltp) / risk : (ltp - entry) / risk;
  return {
    r1: rewardTo(t1),
    r2: rewardTo(t2),
    liveR,
    risk,
  };
}

/**
 * Desk-grade TradingView Lightweight Charts workstation.
 * Pane 1: candles + institutional overlays + call lines
 * Pane 2: volume
 * Pane 3: RSI | MACD | OI
 */
export default function ChartWorkstation({
  symbol,
  signalContext = null,
  defaultInterval = '1d',
}) {
  const priceRef = useRef(null);
  const volRef = useRef(null);
  const indRef = useRef(null);
  const chartsRef = useRef({ price: null, vol: null, ind: null });
  const seriesRef = useRef({});
  const linesRef = useRef([]);
  const syncing = useRef(false);

  const [interval, setIntervalTf] = useState(defaultInterval);
  const [indicator, setIndicator] = useState('rsi');
  const [payload, setPayload] = useState(null);
  const [ltp, setLtp] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showEma, setShowEma] = useState(true);
  const [showVwap, setShowVwap] = useState(true);
  const [showPivots, setShowPivots] = useState(true);
  const [showWalls, setShowWalls] = useState(true);
  const [showCalls, setShowCalls] = useState(true);

  const wallsAvailable = Boolean(payload?.optional_features?.walls?.available);
  const oiAvailable = Boolean(payload?.optional_features?.oi?.available);
  const freshness = payload?.freshness;
  const feedStatus = payload?.status || (payload?.has_data ? 'ok' : 'unavailable');

  const callLevels = useMemo(() => extractCallLevels(signalContext), [signalContext]);
  const rr = useMemo(() => riskReward(callLevels, ltp), [callLevels, ltp]);

  const destroyCharts = useCallback(() => {
    linesRef.current = [];
    Object.values(chartsRef.current).forEach((c) => {
      try {
        c?.remove?.();
      } catch {
        /* ignore */
      }
    });
    chartsRef.current = { price: null, vol: null, ind: null };
    seriesRef.current = {};
  }, []);

  const syncRange = useCallback((source) => {
    if (syncing.current) return;
    syncing.current = true;
    try {
      const range = source.timeScale().getVisibleLogicalRange();
      if (!range) return;
      ['price', 'vol', 'ind'].forEach((key) => {
        const c = chartsRef.current[key];
        if (c && c !== source) {
          c.timeScale().setVisibleLogicalRange(range);
        }
      });
    } finally {
      syncing.current = false;
    }
  }, []);

  const applyPriceLines = useCallback(
    (candleSeries, data) => {
      // Clear old lines by recreating series data path — store refs and remove
      (linesRef.current || []).forEach((ln) => {
        try {
          candleSeries.removePriceLine(ln);
        } catch {
          /* ignore */
        }
      });
      linesRef.current = [];
      const add = (price, color, title, style = 2) => {
        if (price == null || Number.isNaN(Number(price))) return;
        const ln = candleSeries.createPriceLine({
          price: Number(price),
          color,
          lineWidth: 1,
          lineStyle: style, // 0 solid, 2 dashed
          axisLabelVisible: true,
          title,
        });
        linesRef.current.push(ln);
      };

      if (showPivots && data?.previous_day) {
        const pd = data.previous_day;
        add(pd.high, '#fbbf24', 'PDH', 2);
        add(pd.low, '#fbbf24', 'PDL', 2);
        add(pd.close, '#a78bfa', 'PDC', 2);
      }
      if (
        showWalls &&
        data?.optional_features?.walls?.available &&
        data?.walls
      ) {
        add(data.walls.call_wall, '#f07178', 'Call Wall', 0);
        add(data.walls.put_wall, '#3ecf8e', 'Put Wall', 0);
      }
      if (showCalls && callLevels) {
        add(callLevels.entry, '#60a5fa', 'Entry', 0);
        add(callLevels.stop, '#f07178', 'SL', 0);
        add(callLevels.t1, '#3ecf8e', 'T1', 0);
        add(callLevels.t2, '#34d399', 'T2', 0);
      }
    },
    [showPivots, showWalls, showCalls, callLevels],
  );

  const buildCharts = useCallback(
    (data) => {
      if (!priceRef.current || !volRef.current || !indRef.current) return;
      destroyCharts();

      const price = createChart(priceRef.current, {
        ...CHART_OPTS,
        height: 340,
        width: priceRef.current.clientWidth,
      });
      const vol = createChart(volRef.current, {
        ...CHART_OPTS,
        height: 100,
        width: volRef.current.clientWidth,
        timeScale: { ...CHART_OPTS.timeScale, visible: false },
      });
      const ind = createChart(indRef.current, {
        ...CHART_OPTS,
        height: 120,
        width: indRef.current.clientWidth,
      });
      chartsRef.current = { price, vol, ind };

      const candles = price.addCandlestickSeries({
        upColor: '#3ecf8e',
        downColor: '#f07178',
        borderUpColor: '#3ecf8e',
        borderDownColor: '#f07178',
        wickUpColor: '#3ecf8e',
        wickDownColor: '#f07178',
      });
      candles.setData(
        (data.bars || []).map((b) => ({
          time: b.time,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      );
      seriesRef.current.candles = candles;

      if (showEma && data.ema_ribbon) {
        const colors = {
          ema9: '#f472b6',
          ema21: '#60a5fa',
          ema50: '#fbbf24',
          ema200: '#c4b5fd',
        };
        Object.entries(colors).forEach(([key, color]) => {
          const pts = data.ema_ribbon[key] || [];
          if (!pts.length) return;
          const s = price.addLineSeries({
            color,
            lineWidth: key === 'ema200' ? 2 : 1,
            priceLineVisible: false,
            lastValueVisible: false,
            title: key.toUpperCase(),
          });
          s.setData(pts);
          seriesRef.current[key] = s;
        });
      }

      if (showVwap && data.vwap?.series?.length) {
        const vwap = price.addLineSeries({
          color: '#38bdf8',
          lineWidth: 2,
          priceLineVisible: false,
          title: 'VWAP',
        });
        vwap.setData(data.vwap.series);
        seriesRef.current.vwap = vwap;
        const band = (pts, color) => {
          if (!pts?.length) return;
          const s = price.addLineSeries({
            color,
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          s.setData(pts);
        };
        band(data.vwap.band_1_upper_series, 'rgba(56,189,248,0.45)');
        band(data.vwap.band_1_lower_series, 'rgba(56,189,248,0.45)');
        band(data.vwap.band_2_upper_series, 'rgba(56,189,248,0.25)');
        band(data.vwap.band_2_lower_series, 'rgba(56,189,248,0.25)');
      }

      applyPriceLines(candles, data);

      const volSeries = vol.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      });
      volSeries.setData(data.volume || []);
      seriesRef.current.volume = volSeries;

      // Indicator pane
      if (indicator === 'rsi' && data.rsi?.length) {
        const rsi = ind.addLineSeries({ color: '#eab308', lineWidth: 1.5, title: 'RSI' });
        rsi.setData(data.rsi);
        seriesRef.current.rsi = rsi;
        ind.addLineSeries({
          color: 'rgba(255,255,255,0.25)',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        }).setData(data.rsi.map((p) => ({ time: p.time, value: 70 })));
        ind.addLineSeries({
          color: 'rgba(255,255,255,0.25)',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        }).setData(data.rsi.map((p) => ({ time: p.time, value: 30 })));
      } else if (indicator === 'macd' && data.macd) {
        const hist = ind.addHistogramSeries({ title: 'MACD Hist' });
        hist.setData(data.macd.histogram || []);
        const macd = ind.addLineSeries({ color: '#60a5fa', lineWidth: 1.5, title: 'MACD' });
        macd.setData(data.macd.macd || []);
        const sig = ind.addLineSeries({ color: '#f472b6', lineWidth: 1, title: 'Signal' });
        sig.setData(data.macd.signal || []);
        seriesRef.current.macd = macd;
      } else if (indicator === 'oi' && data.oi?.length) {
        const oi = ind.addAreaSeries({
          topColor: 'rgba(167, 139, 250, 0.35)',
          bottomColor: 'rgba(167, 139, 250, 0.02)',
          lineColor: '#a78bfa',
          lineWidth: 2,
          title: 'OI',
        });
        oi.setData(data.oi);
        seriesRef.current.oi = oi;
      } else {
        // Sync-only invisible series — not market data
        ind.addLineSeries({ color: 'transparent' }).setData(
          (data.bars || []).map((b) => ({ time: b.time, value: 0 })),
        );
      }

      price.timeScale().fitContent();
      ['price', 'vol', 'ind'].forEach((key) => {
        chartsRef.current[key]
          ?.timeScale()
          .subscribeVisibleLogicalRangeChange(() =>
            syncRange(chartsRef.current[key]),
          );
      });
    },
    [
      destroyCharts,
      showEma,
      showVwap,
      indicator,
      applyPriceLines,
      syncRange,
    ],
  );

  const load = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await deskAPI.getChart(symbol, {
        interval,
        limit: interval === '1d' ? 250 : 400,
        days: interval === '1d' ? 250 : undefined,
      });
      setPayload(data);
      setLtp(data?.ltp ?? null);
      if (!data?.has_data) {
        setError(data?.message || 'No chart data');
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Chart load failed');
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!payload?.has_data) {
      destroyCharts();
      return undefined;
    }
    buildCharts(payload);
    const onResize = () => {
      const w = priceRef.current?.clientWidth;
      if (!w) return;
      chartsRef.current.price?.applyOptions({ width: w });
      chartsRef.current.vol?.applyOptions({ width: w });
      chartsRef.current.ind?.applyOptions({ width: w });
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      destroyCharts();
    };
  }, [payload, buildCharts, destroyCharts, indicator, showEma, showVwap, showPivots, showWalls, showCalls]);

  // Live poll → series.update
  useEffect(() => {
    if (!symbol || !payload?.has_data) return undefined;
    let alive = true;
    const tick = async () => {
      try {
        const { data } = await deskAPI.getChartLive(symbol, interval);
        if (!alive || !data) return;
        if (data.ltp != null) setLtp(data.ltp);
        const bar = data.bar;
        if (bar && seriesRef.current.candles) {
          seriesRef.current.candles.update({
            time: bar.time,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
          });
          if (seriesRef.current.volume && bar.volume != null) {
            const up = bar.close >= bar.open;
            seriesRef.current.volume.update({
              time: bar.time,
              value: bar.volume,
              color: up ? 'rgba(62, 207, 142, 0.55)' : 'rgba(240, 113, 120, 0.55)',
            });
          }
        }
      } catch {
        /* transient */
      }
    };
    const ms = interval === '1d' ? 30000 : 3000;
    const id = setInterval(tick, ms);
    tick();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [symbol, interval, payload?.has_data]);

  const statusLabel =
    feedStatus === 'stale'
      ? 'STALE'
      : feedStatus === 'aging'
        ? 'AGING'
        : feedStatus === 'unavailable'
          ? 'UNAVAILABLE'
          : freshness?.label || 'OK';

  const statusClass =
    feedStatus === 'stale' || feedStatus === 'unavailable'
      ? 'is-stale'
      : feedStatus === 'aging'
        ? 'is-aging'
        : 'is-ok';

  return (
    <div
      className="chart-ws"
      aria-busy={loading}
      data-status={feedStatus}
      data-testid="chart-workstation"
    >
      <div className="chart-ws__toolbar" role="toolbar" aria-label="Chart controls">
        <div className="chart-ws__intervals" role="group" aria-label="Timeframe">
          {INTERVALS.map((iv) => (
            <button
              key={iv.id}
              type="button"
              className={`chip ${interval === iv.id ? 'is-on' : ''}`}
              aria-pressed={interval === iv.id}
              onClick={() => setIntervalTf(iv.id)}
            >
              {iv.label}
            </button>
          ))}
        </div>
        <div className="chart-ws__toggles">
          <label>
            <input type="checkbox" checked={showEma} onChange={(e) => setShowEma(e.target.checked)} />
            EMA
          </label>
          <label>
            <input
              type="checkbox"
              checked={showVwap}
              onChange={(e) => setShowVwap(e.target.checked)}
              disabled={interval === '1d'}
            />
            VWAP±SD
          </label>
          <label>
            <input type="checkbox" checked={showPivots} onChange={(e) => setShowPivots(e.target.checked)} />
            PDH/L/C
          </label>
          <label title={wallsAvailable ? 'Kotak option-chain walls' : 'Walls unavailable — activate option chain'}>
            <input
              type="checkbox"
              checked={showWalls && wallsAvailable}
              disabled={!wallsAvailable}
              onChange={(e) => setShowWalls(e.target.checked)}
            />
            Walls{!wallsAvailable ? ' (n/a)' : ''}
          </label>
          <label>
            <input type="checkbox" checked={showCalls} onChange={(e) => setShowCalls(e.target.checked)} />
            Call levels
          </label>
        </div>
        <div className="chart-ws__intervals" role="group" aria-label="Indicator pane">
          {IND_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              className={`chip ${indicator === o.id ? 'is-on' : ''}`}
              aria-pressed={indicator === o.id}
              disabled={o.id === 'oi' && !oiAvailable}
              title={
                o.id === 'oi' && !oiAvailable
                  ? 'OI unavailable without Kotak WS bar merge'
                  : undefined
              }
              onClick={() => setIndicator(o.id)}
            >
              {o.label}
              {o.id === 'oi' && !oiAvailable ? ' · n/a' : ''}
            </button>
          ))}
        </div>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="chart-ws__meta" aria-live="polite">
        <span
          className={`live-pill chart-ws__status ${statusClass}`}
          role="status"
          data-testid="chart-status"
        >
          {loading && !payload ? 'LOADING' : statusLabel}
        </span>
        <span>
          {payload?.price_kind === 'eod_close' || payload?.price_kind === 'yahoo_daily_close'
            ? 'Close'
            : 'Last'}{' '}
          <strong>{fmt(ltp)}</strong>
        </span>
        <span className="muted" title={payload?.timezone?.note || ''}>
          TZ Asia/Kolkata
        </span>
        {payload?.previous_day && (
          <span>
            PDC <strong>{fmt(payload.previous_day.close)}</strong>
          </span>
        )}
        {wallsAvailable && payload?.walls?.call_wall != null && (
          <span className="is-down">
            Call Wall <strong>{fmt(payload.walls.call_wall, 0)}</strong>
          </span>
        )}
        {wallsAvailable && payload?.walls?.put_wall != null && (
          <span className="is-up">
            Put Wall <strong>{fmt(payload.walls.put_wall, 0)}</strong>
          </span>
        )}
        {!wallsAvailable && payload?.has_data && (
          <span className="muted" data-testid="walls-unavailable">
            Walls unavailable
          </span>
        )}
        {rr && (
          <span className="chart-ws__rr" title="Live R multiple vs entry/stop">
            Live R <strong className={rr.liveR >= 0 ? 'is-up' : 'is-down'}>{fmt(rr.liveR, 2)}R</strong>
            {rr.r1 != null && <> · T1 {fmt(rr.r1, 2)}R</>}
            {rr.r2 != null && <> · T2 {fmt(rr.r2, 2)}R</>}
          </span>
        )}
        {payload?.source && (
          <span className="muted" data-testid="chart-source">
            src {payload.source}
          </span>
        )}
        {payload?.range?.returned_bars != null && (
          <span className="muted">{payload.range.returned_bars} bars</span>
        )}
        {payload?.missing_bars_skipped > 0 && (
          <span className="muted" title="Null OHLCV timestamps skipped — not filled">
            skipped {payload.missing_bars_skipped} gaps
          </span>
        )}
      </div>

      {loading && !payload && (
        <p className="muted" role="status" data-testid="chart-loading">
          Loading workstation…
        </p>
      )}
      {error && !payload?.has_data && (
        <p className="error-text" role="alert" data-testid="chart-error">
          {error}
        </p>
      )}
      {feedStatus === 'stale' && payload?.has_data && (
        <p className="banner warn chart-ws__banner" role="status">
          Chart bars are stale — last candle age {fmt(freshness?.age_sec, 0)}s. Not live market data.
        </p>
      )}
      {indicator === 'oi' && !oiAvailable && payload?.has_data && (
        <p className="muted" role="status" data-testid="oi-unavailable">
          OI pane unavailable — requires Kotak WS bar merge with open interest.
        </p>
      )}

      <div
        className={`chart-ws__panes ${loading ? 'is-loading' : ''} ${
          !payload?.has_data && !loading ? 'is-empty' : ''
        }`}
        aria-hidden={!payload?.has_data}
      >
        <div className="chart-ws__pane chart-ws__pane--price" ref={priceRef} />
        <div className="chart-ws__label">Volume</div>
        <div className="chart-ws__pane chart-ws__pane--vol" ref={volRef} />
        <div className="chart-ws__label">{indicator.toUpperCase()}</div>
        <div className="chart-ws__pane chart-ws__pane--ind" ref={indRef} />
      </div>
    </div>
  );
}
