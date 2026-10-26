import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deskAPI } from './services/api';
import PickCard from './components/PickCard';
import StockModal from './components/StockModal';
import StockBrowser from './components/StockBrowser';
import BacktestSection from './components/BacktestSection';
import CapitalDesk, { loadCapitalSettings } from './components/CapitalDesk';
import WeekJournal from './components/WeekJournal';
import TradeLedger from './components/TradeLedger';
import PositionSizer from './components/PositionSizer';
import MarketEventsCalendar from './components/MarketEventsCalendar';
import StrategyEvaluation from './components/StrategyEvaluation';
import IntradayDesk from './components/IntradayDesk';
import IndexDesk from './components/IndexDesk';
import McxDesk from './components/McxDesk';
import SignalBoard from './components/SignalBoard';
import SettingsDrawer, {
  loadLlmSettings,
} from './components/SettingsDrawer';
import AuthGate from './components/AuthGate';
import AdminPanel from './components/AdminPanel';
import SignalHistory from './components/SignalHistory';
import SignalAvailabilityBanner from './components/SignalAvailabilityBanner';
import ExpectancyHonestyBanner from './components/ExpectancyHonestyBanner';
import ProvenanceBadge from './components/ProvenanceBadge';
import MarketSessionBanner from './components/MarketSessionBanner';
import { isoWeekLabel } from './isoWeek';
import './App.css';

export { isoWeekLabel } from './isoWeek';

const DESKS = [
  {
    id: 'swing',
    label: 'Swing',
    blurb: 'Weekly NSE momentum',
    tape: 'WEEKLY',
  },
  {
    id: 'intraday',
    label: 'Intraday',
    blurb: 'Live NSE cash bias',
    tape: 'SESSION',
  },
  {
    id: 'index',
    label: 'Index',
    blurb: 'Nifty · BankNifty',
    tape: 'INDEX',
  },
  {
    id: 'mcx',
    label: 'MCX',
    blurb: 'Commodities tape',
    tape: 'FUTURES',
  },
];

function regimeClass(regime) {
  if (regime === 'STRONG_BULL' || regime === 'BULL') return 'regime--bull';
  if (regime === 'BEAR') return 'regime--bear';
  return 'regime--neutral';
}

export default function App() {
  const [picks, setPicks] = useState(null);
  const [regime, setRegime] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  /** Accept symbol string or { symbol, signalContext } from SignalBoard */
  const openSymbol = useCallback((payload) => {
    if (!payload) return;
    if (typeof payload === 'string') {
      setSelected(payload);
      return;
    }
    const sym = payload.symbol || payload;
    if (!sym) return;
    setSelected({
      symbol: sym,
      signalContext: payload.signalContext || payload.context || null,
    });
  }, []);
  const [kotak, setKotak] = useState(null);
  const [kotakFeed, setKotakFeed] = useState(null);
  const [ingestMeta, setIngestMeta] = useState(null);
  const [feedTest, setFeedTest] = useState(null);
  const [testingFeed, setTestingFeed] = useState(null);
  const [query, setQuery] = useState('');
  const [searchHits, setSearchHits] = useState([]);
  const [chipInfo, setChipInfo] = useState(null);
  const [capital, setCapital] = useState(() => loadCapitalSettings());
  const [journalFocus, setJournalFocus] = useState(null);
  const [desk, setDesk] = useState(() => {
    try {
      return localStorage.getItem('swing_desk_mode') || 'swing';
    } catch {
      return 'swing';
    }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [authUser, setAuthUser] = useState(null);
  const [llmSettings, setLlmSettings] = useState(() => loadLlmSettings());
  const [vaultConfigured, setVaultConfigured] = useState(false);
  const [swingCalls, setSwingCalls] = useState(null);
  const [swingCallsErr, setSwingCallsErr] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const capitalRef = useRef(capital);
  const pollRef = useRef(null);
  const searchTimer = useRef(null);
  capitalRef.current = capital;

  const explainChip = (id, title, body, { scrollTo } = {}) => {
    setChipInfo((prev) => (prev?.id === id ? null : { id, title, body }));
    if (scrollTo) {
      requestAnimationFrame(() => {
        document.getElementById(scrollTo)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  };

  const loadDesk = useCallback(async (settings) => {
    const s = settings || capitalRef.current;
    setError(null);
    try {
      const [p, r, st, k, kf, ing] = await Promise.all([
        deskAPI.getWeeklyPicks({
          capital: s.capital,
          risk_pct: s.riskPct,
          max_positions: s.maxPositions,
          reserved_cash_pct: s.reservedCashPct,
          entry_style: s.entryStyle,
          target_gain_pct: s.targetGainPct,
        }),
        deskAPI.getMarketRegime(),
        deskAPI.getStats(),
        deskAPI.kotakStatus().catch(() => ({ data: null })),
        deskAPI.kotakFeedStatus().catch(() => ({ data: null })),
        deskAPI.ingestStatus().catch(() => ({ data: null })),
      ]);
      setPicks(p.data);
      setRegime(r.data);
      setStats(st.data);
      setKotak(k.data);
      setKotakFeed(kf.data);
      setIngestMeta(ing.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to load desk');
    } finally {
      setLoading(false);
    }
  }, []);

  const onCapitalChange = useCallback(
    (settings) => {
      setCapital(settings);
      setLoading(true);
      loadDesk(settings);
    },
    [loadDesk],
  );

  const runFeedTest = async () => {
    setTestingFeed('kotak');
    setFeedTest(null);
    try {
      const { data } = await deskAPI.testKotak();
      setFeedTest({ ...data, which: 'kotak' });
      setKotak(data.status || kotak);
    } catch (e) {
      setFeedTest({
        ok: false,
        which: 'kotak',
        message: e.response?.data?.detail || e.message || 'kotak test failed',
      });
    } finally {
      setTestingFeed(null);
    }
  };

  useEffect(() => {
    loadDesk();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadDesk]);

  const loadSwingConsultant = useCallback(async () => {
    try {
      const { data } = await deskAPI.getSwingConsultant();
      setSwingCalls(data);
      setSwingCallsErr(null);
    } catch (e) {
      setSwingCalls(null);
      setSwingCallsErr(e.response?.data?.detail || e.message || null);
    }
  }, []);

  useEffect(() => {
    if (desk === 'swing') loadSwingConsultant();
  }, [desk, loadSwingConsultant]);

  const onAnalyzeSignal = useCallback(async (signal) => {
    const settings = loadLlmSettings();
    setLlmSettings(settings);
    setAnalyzing(true);
    setAnalysis({ signal, loading: true });
    try {
      const isLocal = settings.provider === 'local';
      const { data } = await deskAPI.analyzeSignal({
        provider: settings.provider,
        model: settings.model,
        signal,
        // Local Ollama/LM Studio needs no vault key; cloud uses vault when configured.
        useStoredKey: !isLocal,
      });
      const result =
        data?.analysis && typeof data.analysis === 'object'
          ? {
              ...data.analysis,
              disclaimer: data.disclaimer || data.analysis.disclaimer,
              ai_generated: data.ai_generated,
              label: data.label,
              cited_inputs: data.cited_inputs,
            }
          : data;
      setAnalysis({ signal, result, loading: false });
      setVaultConfigured(true);
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || 'Analysis failed';
      if (String(detail).toLowerCase().includes('api key')) {
        setSettingsOpen(true);
      }
      setAnalysis({
        signal,
        loading: false,
        error: detail,
      });
    } finally {
      setAnalyzing(false);
    }
  }, []);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!query || query.trim().length < 1) {
      setSearchHits([]);
      return undefined;
    }
    searchTimer.current = setTimeout(async () => {
      try {
        const { data } = await deskAPI.searchStocks(query.trim());
        const rows = Array.isArray(data) ? data : data?.results || [];
        setSearchHits(rows.slice(0, 8));
      } catch {
        setSearchHits([]);
      }
    }, 220);
    return () => clearTimeout(searchTimer.current);
  }, [query]);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollProgress = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await deskAPI.getIngestProgress();
        setProgress(data);
        if (!data.running && (data.phase === 'done' || data.phase === 'error')) {
          stopPolling();
          setIngesting(false);
          if (data.phase === 'error') {
            setError(data.error || data.message || 'Refresh failed');
          }
          await loadDesk();
          loadSwingConsultant();
        }
      } catch {
        // keep polling briefly
      }
    }, 800);
  };

  const refreshData = async (force = false) => {
    setIngesting(true);
    setError(null);
    setProgress({
      running: true,
      percent: 0,
      message: 'Starting refresh…',
      phase: 'starting',
    });
    try {
      const { data } = await deskAPI.ingestLatest(force);
      if (data.status === 'busy') {
        setProgress(data.progress);
        pollProgress();
        return;
      }
      if (data.status === 'started') {
        pollProgress();
        return;
      }
      setProgress({ running: false, percent: 100, message: data.message, phase: 'done' });
      setIngesting(false);
      await loadDesk();
      loadSwingConsultant();
    } catch (e) {
      stopPolling();
      setIngesting(false);
      setError(e.response?.data?.detail || e.message || 'Ingest failed');
    }
  };

  const dataStatus = picks?.data_status || regime?.data_status || stats?.freshness;
  const provenance = picks?.provenance || stats?.provenance;
  const isDemo = provenance?.is_demo || provenance?.data_source === 'demo';
  const candidates = picks?.candidates || [];
  const radar = picks?.radar || [];
  const goalPlan = picks?.goal_plan;
  // Hero / journal / planner use *calendar* ISO week (today), not EOD as-of week.
  // Last Friday's bars are still week 43 while Monday trading week is already 44.
  const weekLabel =
    picks?.calendar_week_label || isoWeekLabel();
  const dataWeekLabel =
    picks?.as_of_week_label ||
    picks?.goal_plan?.week_label ||
    picks?.week_label ||
    null;
  const isStale = dataStatus?.status === 'STALE' || picks?.status === 'stale';
  const isCash = picks?.status === 'cash' || candidates.length === 0;
  const coverage = stats?.coverage || {};

  const goalHints = useMemo(() => {
    const map = {};
    const suggested =
      goalPlan?.suggested_candidates || goalPlan?.suggested || [];
    suggested.forEach((s) => {
      if (s?.symbol) {
        map[s.symbol] = {
          ...s,
          potential_reward_rs:
            s.potential_reward_rs ?? s.theoretical_reward_rs,
        };
      }
    });
    return map;
  }, [goalPlan]);

  const onLogTrade = useCallback((symbol) => {
    setJournalFocus(symbol);
    setDesk('swing');
    try {
      localStorage.setItem('swing_desk_mode', 'swing');
    } catch {
      /* ignore */
    }
  }, []);

  const switchDesk = (id) => {
    setDesk(id);
    try {
      localStorage.setItem('swing_desk_mode', id);
    } catch {
      /* ignore */
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const categoryForDesk =
    desk === 'mcx'
      ? 'commodity'
      : desk === 'intraday' || desk === 'index'
        ? 'intraday'
        : 'swing';

  return (
    <AuthGate
      onUser={(u) => {
        setAuthUser(u);
        if (u) {
          deskAPI
            .llmVaultStatus()
            .then((r) => setVaultConfigured(!!r.data?.configured))
            .catch(() => setVaultConfigured(false));
        }
      }}
    >
    <div className="desk">
      <div className="desk__atmosphere" aria-hidden />
      <MarketSessionBanner />
      {(() => {
        const isDemo =
          stats?.provenance?.is_demo ||
          stats?.provenance?.data_source === 'demo' ||
          picks?.provenance?.is_demo;
        const src =
          stats?.provenance?.data_source ||
          picks?.provenance?.data_source ||
          (kotak?.configured ? 'kotak' : 'unknown');
        if (isDemo) {
          return (
            <div className="demo-banner" role="alert">
              <ProvenanceBadge dataMode="error" note="Synthetic EOD in DB" />
              <span>
                DEMO provenance detected — forbidden. Run Force full with Kotak. Refusing to
                treat these closes as live.
              </span>
            </div>
          );
        }
        return (
          <div className="demo-banner demo-banner--live" role="status">
            <ProvenanceBadge
              priceKind="eod_close"
              note={`Swing/stock cards use ${src} EOD close — not LTP`}
            />
            <span>
              Personal desk · live adapter only · Swing=EOD · Intraday/Index=LTP · no execution
            </span>
          </div>
        );
      })()}

      <header className="desk__nav">
        <div className="brand">
          <span className="brand__mark" />
          <span className="brand__name">Swing Desk</span>
        </div>
        <nav className="desk-tabs" role="tablist" aria-label="Trading desks">
          {DESKS.map((d) => (
            <button
              key={d.id}
              type="button"
              role="tab"
              aria-selected={desk === d.id}
              className={`desk-tab desk-tab--${d.id} ${desk === d.id ? 'is-active' : ''}`}
              onClick={() => switchDesk(d.id)}
              title={d.blurb}
            >
              <span className="desk-tab__tape">{d.tape}</span>
              <span className="desk-tab__label">{d.label}</span>
              <span className="desk-tab__blurb">{d.blurb}</span>
            </button>
          ))}
        </nav>
        <div className="nav-search">
          <input
            type="search"
            placeholder="Search NSE symbol…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search stocks"
          />
          {searchHits.length > 0 && (
            <ul className="search-hits">
              {searchHits.map((h) => {
                const sym = h.symbol || h;
                return (
                  <li key={sym}>
                    <button type="button" onClick={() => { setSelected(sym); setQuery(''); setSearchHits([]); }}>
                      {sym}
                      {h.sector ? <span>{h.sector}</span> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="nav-actions">
          {authUser &&
          (authUser.auth_enabled === false ||
            (authUser.role === 'admin' &&
              authUser.email !== 'operator@local')) ? (
            <button
              type="button"
              className="btn ghost"
              onClick={() => setAdminOpen(true)}
              title="Publish optional research notes to the Signal ledger (not desk auto-feed)"
            >
              Publish notes
            </button>
          ) : null}
          <button
            type="button"
            className={`btn ghost ${vaultConfigured ? 'btn--keyed' : ''}`}
            onClick={() => setSettingsOpen(true)}
            title={
              vaultConfigured
                ? `LLM vault · ${llmSettings.model || llmSettings.provider}`
                : 'Configure encrypted LLM key (server vault)'
            }
          >
            {vaultConfigured ? 'LLM · vault' : 'Settings'}
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={runFeedTest}
            disabled={!!testingFeed || ingesting}
          >
            {testingFeed === 'kotak' ? 'Testing…' : 'Test Kotak'}
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => refreshData(true)}
            disabled={ingesting}
            title="Full Kotak refresh of liquid NSE universe"
          >
            Force full
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => refreshData(false)}
            disabled={ingesting}
          >
            {ingesting ? 'Updating…' : 'Refresh data'}
          </button>
        </div>
      </header>

      {ingesting && progress && (
        <div className="progress-bar" role="status" aria-live="polite">
          <div className="progress-bar__track">
            <div
              className="progress-bar__fill"
              style={{ width: `${Math.max(4, progress.percent || 0)}%` }}
            />
          </div>
          <p className="progress-bar__label">
            <span className="progress-bar__pct">{progress.percent ?? 0}%</span>
            <span className="progress-bar__msg">
              {progress.message || progress.phase || 'Working…'}
            </span>
          </p>
        </div>
      )}

      <main className="desk__hero">
        <div className="hero__copy">
          {desk === 'swing' && (
            <>
          <p className="eyebrow">India Elite Momentum · NSE liquid equities</p>
          <div className="hero__week" aria-label={`ISO week ${weekLabel}`}>
            <span className="hero__week-label">Week</span>
            <span className="hero__week-value">{weekLabel}</span>
            {dataWeekLabel && dataWeekLabel !== weekLabel ? (
              <span className="hero__week-asof muted" title="ISO week of latest EOD bar">
                data {dataWeekLabel}
              </span>
            ) : null}
          </div>
          <h1 className="hero__title">This week&apos;s setups</h1>
          <p className="hero__sub">
            Enter capital + the weekly % you want to chase. The desk sizes risk, checks
            whether India Elite Momentum setups can even approach that goal, and ranks
            this week&apos;s names — research math, not a tip channel.
          </p>
            </>
          )}
          {desk === 'intraday' && (
            <>
              <p className="eyebrow">NSE cash · 5m live bias</p>
              <h1 className="hero__title">Intraday desk</h1>
              <p className="hero__sub">
                Realtime-polled long/short bias for liquid NSE names. Session-aware —
                outside market hours you see last-session residue. Hard stops; small size.
              </p>
            </>
          )}
          {desk === 'index' && (
            <>
              <p className="eyebrow">Nifty · BankNifty · multi-timeframe</p>
              <h1 className="hero__title">Index desk</h1>
              <p className="hero__sub">
                Live index bias from daily SMA regime + 5m EMA/VWAP/RSI, plus Kotak
                option-chain PCR / walls when the feed is live. Size F&amp;O risk yourself.
              </p>
            </>
          )}
          {desk === 'mcx' && (
            <>
              <p className="eyebrow">Commodities · global futures proxy (not MCX INR)</p>
              <h1 className="hero__title">Commodities desk</h1>
              <p className="hero__sub">
                Yahoo continuous futures (usually USD) + USDINR — not INR MCX contracts.
                Related MCX names are hints only; this app does not size lots or place orders.
              </p>
            </>
          )}

          {desk === 'swing' && (
          <>
          <div className="hero__meta" role="group" aria-label="Desk status — click for details">
            {regime && (
              <button
                type="button"
                className={`regime meta-chip--btn ${regimeClass(regime.regime)} ${chipInfo?.id === 'regime' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'regime',
                    `Market regime · ${regime.regime?.replace('_', ' ')}`,
                    [
                      regime.reason,
                      regime.allow_trading
                        ? 'New swing entries are allowed this week.'
                        : 'New entries are blocked — cash until NIFTY regime improves.',
                      regime.nifty_price != null
                        ? `NIFTY ${regime.nifty_price.toFixed(0)}${
                            regime.nifty_sma_20 != null ? ` · SMA20 ${regime.nifty_sma_20.toFixed(0)}` : ''
                          }${
                            regime.nifty_sma_50 != null ? ` · SMA50 ${regime.nifty_sma_50.toFixed(0)}` : ''
                          }`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(' '),
                    { scrollTo: 'section-regime' },
                  )
                }
              >
                <span className="regime__dot" />
                {regime.regime?.replace('_', ' ')}
              </button>
            )}
            {isDemo && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn meta-chip--demo ${chipInfo?.id === 'demo' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'demo',
                    'Forbidden demo EOD',
                    'Synthetic seed detected in DB. Phase 1 refuses demo. Run Force full with Kotak.',
                  )
                }
              >
                DEMO FORBIDDEN
              </button>
            )}
            {!isDemo && provenance?.data_source && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn meta-chip--live ${chipInfo?.id === 'source' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'source',
                    `${String(provenance.data_source).toUpperCase()} data`,
                    provenance.data_note ||
                      `End-of-day candles come from ${String(provenance.data_source).toUpperCase()}. Financial ratios on stock click come from Screener.in (cached).`,
                  )
                }
              >
                {String(provenance.data_source).toUpperCase()} data
              </button>
            )}
            {kotak && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn ${kotak.configured ? 'meta-chip--live' : 'meta-chip--demo'} ${chipInfo?.id === 'kotak' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'kotak',
                    kotak.configured ? 'Kotak Neo ready' : 'Kotak Neo off',
                    kotak.configured
                      ? `${kotak.note || 'Historical EOD uses your Neo Trade API consumer key.'} Use Test Kotak to probe, or Force full to refresh up to ${stats?.ingest_cap || 500} liquid names.`
                      : 'Add KOTAK_CONSUMER_KEY in backend/.env (Neo → More → Trade API), restart API, then Test Kotak.',
                  )
                }
              >
                Kotak {kotak.configured ? 'ready' : 'off'}
              </button>
            )}
            {kotakFeed && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn ${
                  kotakFeed?.ws?.connected ? 'meta-chip--live' : 'meta-chip--demo'
                } ${chipInfo?.id === 'kotakws' ? 'is-active' : ''}`}
                onClick={() => {
                  const ws = kotakFeed.ws || {};
                  const pol = kotakFeed.provider_policy || {};
                  const fb = pol.yahoo_ltp_fallback_allowed !== false;
                  explainChip(
                    'kotakws',
                    ws.connected ? 'Kotak WS connected' : 'Kotak WS off',
                    ws.connected
                      ? `Broker LTP path active (${ws.protocol || 'native_batch'}). Quotes cached: ${kotakFeed.quotes_cached ?? 0}. Depth/F&O subscribe paths exist in code — not live-verified in this build.`
                      : `No broker stream. Intraday/Index use Yahoo research FALLBACK (never labeled broker LIVE) when ALLOW_YAHOO_LTP_FALLBACK=${fb ? 'true' : 'false'}. Login via POST /api/kotak/session/login (TOTP) to start WS.`,
                  );
                }}
              >
                WS {kotakFeed?.ws?.connected ? 'LIVE' : 'off'}
                {kotakFeed?.provider_policy?.yahoo_ltp_fallback_allowed === false
                  ? ' · no Yahoo'
                  : ''}
              </button>
            )}
            {dataStatus?.latest_date && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn ${chipInfo?.id === 'eod' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'eod',
                    `EOD ${dataStatus.latest_date} · ${dataStatus.status || '—'}`,
                    [
                      dataStatus.message,
                      dataStatus.expected_as_of
                        ? `Expected session ${dataStatus.expected_as_of} (${dataStatus.age_unit || 'trading_days'} age ${dataStatus.age_days ?? '—'}).`
                        : null,
                      dataStatus.holiday_list_complete === false
                        ? 'Holiday list incomplete — verify NSE circular.'
                        : null,
                      'STALE → Refresh / Force full or wait for scheduled post-close ingest.',
                    ]
                      .filter(Boolean)
                      .join(' '),
                  )
                }
              >
                EOD {dataStatus.latest_date}
                {dataStatus.status ? ` · ${dataStatus.status}` : ''}
              </button>
            )}
            {ingestMeta?.scheduler && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn ${
                  ingestMeta.scheduler.schedule_enabled ? 'meta-chip--live' : 'meta-chip--demo'
                } ${chipInfo?.id === 'eodsched' ? 'is-active' : ''}`}
                onClick={() => {
                  const sch = ingestMeta.scheduler || {};
                  const j = ingestMeta.journal?.last_success || {};
                  const cal = ingestMeta.calendar || {};
                  explainChip(
                    'eodsched',
                    sch.schedule_enabled ? `EOD schedule ${sch.time_ist || ''} IST` : 'EOD schedule off',
                    [
                      sch.schedule_enabled
                        ? `Runs ~${sch.time_ist} IST on trading days (settle ${sch.settle_ist}).`
                        : 'Set EOD_INGEST_SCHEDULE_ENABLED=true to enable.',
                      cal.expected_eod_as_of
                        ? `Expected EOD ${cal.expected_eod_as_of}.`
                        : null,
                      j.finished_at
                        ? `Last success: session ${j.target_session || '—'} via ${j.provider || '—'}.`
                        : 'No successful ingest recorded yet.',
                      ingestMeta.journal?.last_run?.status === 'error'
                        ? `Last error: ${ingestMeta.journal.last_run.error || ingestMeta.journal.last_run.message || 'failed'}`
                        : null,
                      cal.limitation ||
                        'Holidays from operator-maintained snapshot — not live NSE sync.',
                    ]
                      .filter(Boolean)
                      .join(' '),
                  );
                }}
              >
                Sched {ingestMeta.scheduler.schedule_enabled ? ingestMeta.scheduler.time_ist || 'on' : 'off'}
              </button>
            )}
            <button
              type="button"
              className={`meta-chip meta-chip--btn ${chipInfo?.id === 'coverage' ? 'is-active' : ''}`}
              onClick={() =>
                explainChip(
                  'coverage',
                  'Coverage',
                  [
                    `${stats?.symbol_count ?? 0} symbols have local EOD in the desk database.`,
                    coverage.listed_eq_approx
                      ? `Browse lists ~${coverage.listed_eq_approx} NSE EQ cash names (financials on click even without EOD).`
                      : null,
                    stats?.ingest_cap
                      ? `Force full refreshes up to ${stats.ingest_cap} liquid names per run (Kotak rate limits).`
                      : null,
                    coverage.note || null,
                  ]
                    .filter(Boolean)
                    .join(' '),
                  { scrollTo: 'section-stocks' },
                )
              }
            >
              {stats ? `${stats.symbol_count ?? 0} EOD` : 'EOD —'}
              {coverage.listed_eq_approx ? ` · ${coverage.listed_eq_approx} NSE EQ` : ''}
              {stats?.ingest_cap ? ` · refresh ${stats.ingest_cap}` : ''}
            </button>
          </div>

          {chipInfo && (
            <div className="chip-detail" role="status">
              <div>
                <strong>{chipInfo.title}</strong>
                <p>{chipInfo.body}</p>
              </div>
              <button type="button" className="btn ghost" onClick={() => setChipInfo(null)}>
                Dismiss
              </button>
            </div>
          )}

          <div className="hero-planner">
            <CapitalDesk
              value={capital}
              onChange={onCapitalChange}
              goalPlan={goalPlan}
              weekLabel={weekLabel}
            />
          </div>
          </>
          )}
        </div>

        {desk === 'swing' && (
          <>
        {loading && <p className="muted hero-status">Loading desk…</p>}
        {error && <p className="error-text hero-status">{error}</p>}

        {feedTest && (
          <div className={`banner ${feedTest.ok ? 'info' : 'warn'}`}>
            {feedTest.ok
              ? `${(feedTest.which || 'feed').toUpperCase()} connected. `
              : `${(feedTest.which || 'feed').toUpperCase()} test failed. `}
            {feedTest.message}
          </div>
        )}

        {isDemo && !loading && (
          <div className="banner warn" role="alert">
            Synthetic DEMO EOD detected — forbidden. Run <em>Force full</em> with Kotak. No
            mock prices will be treated as live.
          </div>
        )}

        {isStale && !loading && !isDemo && (
          <SignalAvailabilityBanner
            availability={{
              code: 'data_blocked',
              label: 'Signal evaluation blocked — data stale or unavailable',
              detail: `EOD candles are stale vs expected trading session${
                dataStatus?.expected_as_of ? ` (${dataStatus.expected_as_of})` : ''
              }. Refresh / Force full, or wait for scheduled post-close ingest. Stale data never produces a fresh swing signal.`,
            }}
          />
        )}

        {!loading && regime && !regime.allow_trading && (
          <div className="banner cash-banner">
            <strong>No qualifying signal — strategy conditions not met</strong>
            <p>
              Cash week — {regime.regime?.replace('_', ' ')}. {picks?.message || regime.reason}{' '}
              Intentional risk control, not a broken feed — switch to <em>Intraday</em> or{' '}
              <em>MCX</em> for live desks, or study the momentum radar below.
            </p>
            {regime.nifty_price != null && (
              <p className="cash-banner__levels">
                NIFTY {regime.nifty_price.toFixed(0)}
                {regime.nifty_sma_20 != null && ` · SMA20 ${regime.nifty_sma_20.toFixed(0)}`}
                {regime.nifty_sma_50 != null && ` · SMA50 ${regime.nifty_sma_50.toFixed(0)}`}
                {' · '}
                new swing entries blocked until regime improves
              </p>
            )}
          </div>
        )}

        {!loading && !isStale && isCash && regime?.allow_trading && (
          <SignalAvailabilityBanner
            availability={{
              code: 'no_qualifying',
              label: 'No qualifying signal — strategy conditions not met',
              detail: picks?.message || 'No setups meet criteria — stay in cash.',
            }}
          />
        )}

        <div className="picks-row">
          {candidates.map((c, i) => (
            <PickCard
              key={c.symbol}
              pick={c}
              index={i}
              onOpen={openSymbol}
              onLogTrade={onLogTrade}
              goalHint={goalHints[c.symbol]}
            />
          ))}
          {!loading && candidates.length === 0 && !isStale && (
            <div className="empty-picks">
              <p>
                {regime?.allow_trading
                  ? 'No qualified swing this week.'
                  : 'Watch the radar below — no new swing entries while regime is weak. Use Intraday / MCX tabs for live tapes.'}
              </p>
            </div>
          )}
        </div>
          </>
        )}

        {desk === 'intraday' && (
          <IntradayDesk onOpen={openSymbol} onAnalyze={onAnalyzeSignal} />
        )}
        {desk === 'index' && (
          <IndexDesk onOpen={openSymbol} onAnalyze={onAnalyzeSignal} />
        )}
        {desk === 'mcx' && <McxDesk onAnalyze={onAnalyzeSignal} />}
      </main>

      {desk === 'swing' && (
      <div className="desk__below">
        {swingCalls &&
          ((swingCalls.signals || swingCalls.calls)?.length > 0 ||
            swingCalls.signal_availability) && (
          <section className="section consultant-swing" id="section-consultant-swing">
            <ExpectancyHonestyBanner
              desk="swing"
              honesty={swingCalls.expectancy_honesty}
            />
            <SignalBoard
              title="Weekly consultant calls"
              subtitle="Deterministic research cards from the swing strategy — not tips, not the Signal ledger."
              signals={swingCalls.signals || swingCalls.calls}
              desk="swing"
              source={swingCalls._source || 'consultant'}
              availability={swingCalls.signal_availability}
              onOpen={openSymbol}
              onAnalyze={onAnalyzeSignal}
            />
            {swingCalls.disclaimer && (
              <p className="muted capital-desk__disclaimer">{swingCalls.disclaimer}</p>
            )}
          </section>
        )}

        {swingCallsErr && (
          <p className="muted consultant-swing__miss">
            Consultant swing feed unavailable — using classic picks above.
          </p>
        )}

        <TradeLedger />

        <PositionSizer />

        <MarketEventsCalendar />

        <StrategyEvaluation />

        <WeekJournal
          weekLabel={weekLabel}
          picks={candidates}
          candidates={candidates.length ? candidates : radar}
          focusSymbol={journalFocus}
          onFocusConsumed={() => setJournalFocus(null)}
        />

        {radar.length > 0 && (
          <section className="section radar-section">
            <h3>Momentum radar</h3>
            <p className="section-sub">
              Highest scores in the scanned universe
              {!regime?.allow_trading ? ' — not actionable while swing entries are blocked' : ''}.
            </p>
            <div className="radar-grid">
              {radar.map((r) => (
                <button
                  key={r.symbol}
                  type="button"
                  className="radar-card"
                  onClick={() => openSymbol(r.symbol)}
                >
                  <span className="radar-card__sym">{r.symbol}</span>
                  <span className="radar-card__score">{r.score}</span>
                  <span className="radar-card__meta">
                    ₹{r.close} · RSI {r.rsi_14} · RS {r.relative_strength > 0 ? '+' : ''}
                    {r.relative_strength}%
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        <StockBrowser onOpen={openSymbol} />

        {regime && (
          <section className="section regime-detail" id="section-regime">
            <h3>Market regime</h3>
            <p>{regime.reason}</p>
            {regime.nifty_price != null && (
              <div className="stat-grid compact">
                <div>
                  <span>NIFTY</span>
                  <strong>{regime.nifty_price?.toFixed?.(0)}</strong>
                </div>
                <div>
                  <span>20D change</span>
                  <strong className={regime.nifty_change_20d >= 0 ? 'pos' : 'neg'}>
                    {regime.nifty_change_20d?.toFixed?.(2)}%
                  </strong>
                </div>
                <div>
                  <span>Entries</span>
                  <strong>{regime.allow_trading ? 'Allowed' : 'Blocked'}</strong>
                </div>
                <div>
                  <span>Coverage</span>
                  <strong>
                    {stats?.symbol_count ?? 0}
                    {stats?.ingest_cap ? ` / ${stats.ingest_cap}` : ''}
                  </strong>
                </div>
              </div>
            )}
          </section>
        )}

        <BacktestSection />
        <SignalHistory
          category={categoryForDesk}
          onOpen={(s) =>
            openSymbol({
              symbol: s.symbol,
              signalContext: {
                direction: s.direction,
                rationale: s.rationale,
                data_mode: s.data_mode,
                status: s.status,
                evidence: s.evidence,
              },
            })
          }
        />
      </div>
      )}

      {(desk === 'intraday' || desk === 'index' || desk === 'mcx') && (
        <div className="desk__body">
          <SignalHistory
            category={categoryForDesk}
            onOpen={(s) =>
              openSymbol({
                symbol: s.symbol,
                signalContext: {
                  direction: s.direction,
                  rationale: s.rationale,
                  data_mode: s.data_mode,
                  status: s.status,
                  evidence: s.evidence,
                },
              })
            }
          />
        </div>
      )}

      <footer className="desk__foot">
        Educational research desk — not investment advice and not a profit guarantee. Past
        backtests and published momentum edges do not ensure future results. Browse covers
        listed NSE EQ; scans use liquid EOD (Kotak). Financials from Screener.in (cached).
        Always use the hard stop; never risk money you cannot afford to lose. Jurisdiction
        and regulatory posture are configurable — this product does not claim compliance
        in every market.
      </footer>

      {selected && (
        <StockModal
          symbol={typeof selected === 'string' ? selected : selected.symbol}
          signalContext={
            typeof selected === 'object' ? selected.signalContext || null : null
          }
          onClose={() => setSelected(null)}
        />
      )}

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={(s) => {
          setLlmSettings(s);
          setVaultConfigured(!!s?.vaultConfigured || vaultConfigured);
          deskAPI
            .llmVaultStatus()
            .then((r) => setVaultConfigured(!!r.data?.configured))
            .catch(() => {});
        }}
      />

      <AdminPanel open={adminOpen} onClose={() => setAdminOpen(false)} />

      {analysis && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !analyzing && setAnalysis(null)}
        >
          <div
            className="modal modal--wide analysis-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="analysis-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="modal__head">
              <div>
                <h2 id="analysis-title">
                  AI commentary
                  {analysis.signal?.symbol
                    ? ` · ${analysis.signal.symbol}`
                    : ''}
                </h2>
                <p>
                  {analysis.result?.label ||
                    'AI-GENERATED COMMENTARY — not an authoritative trading signal.'}
                </p>
              </div>
              <button
                type="button"
                className="btn ghost"
                disabled={analyzing}
                onClick={() => setAnalysis(null)}
              >
                Close
              </button>
            </header>
            {(analysis.loading || analyzing) && (
              <p className="muted">Running analysis…</p>
            )}
            {analysis.error && (
              <p className="error-text">{String(analysis.error)}</p>
            )}
            {analysis.result && (
              <div className="analysis-body">
                {analysis.result.summary && (
                  <p className="analysis-body__summary">{analysis.result.summary}</p>
                )}
                {analysis.result.bull_case && (
                  <div>
                    <h4>Bull case</h4>
                    <p>{analysis.result.bull_case}</p>
                  </div>
                )}
                {analysis.result.bear_case && (
                  <div>
                    <h4>Bear case</h4>
                    <p>{analysis.result.bear_case}</p>
                  </div>
                )}
                {analysis.result.risks && (
                  <div>
                    <h4>Risks</h4>
                    <p>
                      {Array.isArray(analysis.result.risks)
                        ? analysis.result.risks.join(' · ')
                        : analysis.result.risks}
                    </p>
                  </div>
                )}
                {Array.isArray(analysis.result.checklist) &&
                  analysis.result.checklist.length > 0 && (
                    <div>
                      <h4>Checklist</h4>
                      <ul>
                        {analysis.result.checklist.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                {(analysis.result.disclaimer || analysis.result.analysis?.disclaimer) && (
                  <p className="muted analysis-body__disclaimer">
                    {analysis.result.disclaimer ||
                      analysis.result.analysis?.disclaimer}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
    </AuthGate>
  );
}
