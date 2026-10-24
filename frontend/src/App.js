import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deskAPI } from './services/api';
import PickCard from './components/PickCard';
import StockModal from './components/StockModal';
import StockBrowser from './components/StockBrowser';
import BacktestSection from './components/BacktestSection';
import CapitalDesk, { loadCapitalSettings } from './components/CapitalDesk';
import WeekJournal from './components/WeekJournal';
import IntradayDesk from './components/IntradayDesk';
import McxDesk from './components/McxDesk';
import SignalBoard from './components/SignalBoard';
import SettingsDrawer, {
  loadLlmSettings,
} from './components/SettingsDrawer';
import AuthGate from './components/AuthGate';
import AdminPanel from './components/AdminPanel';
import SignalHistory from './components/SignalHistory';
import ProvenanceBadge from './components/ProvenanceBadge';
import './App.css';

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

/** Client-side ISO week label e.g. 2026-W43 */
export function isoWeekLabel(date = new Date()) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
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
      const [p, r, st, k] = await Promise.all([
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
      ]);
      setPicks(p.data);
      setRegime(r.data);
      setStats(st.data);
      setKotak(k.data);
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
      const { data } = await deskAPI.analyzeSignal({
        provider: settings.provider,
        model: settings.model,
        signal,
        useStoredKey: true,
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
  const weekLabel =
    picks?.goal_plan?.week_label || picks?.week_label || isoWeekLabel();
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
    desk === 'mcx' ? 'commodity' : desk === 'intraday' ? 'intraday' : 'swing';

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
      {(() => {
        const isDemo =
          stats?.provenance?.is_demo ||
          stats?.provenance?.data_source === 'demo' ||
          picks?.provenance?.is_demo;
        const src =
          stats?.provenance?.data_source ||
          picks?.provenance?.data_source ||
          (kotak?.configured ? 'kotak' : 'unknown');
        return (
          <div
            className={`demo-banner ${isDemo ? '' : 'demo-banner--live'}`}
            role="status"
          >
            <ProvenanceBadge
              dataMode={isDemo ? 'demo' : 'delayed'}
              note={
                isDemo
                  ? 'Sample/demo EOD — run Force full with Kotak for live session closes.'
                  : `EOD from ${src} (previous session close — not live LTP).`
              }
            />
            <span>
              {isDemo
                ? 'Demo mode on. Set ALLOW_DEMO_DATA=false and refresh Kotak for personal live EOD.'
                : 'Personal desk: real Kotak EOD + rule-based calls. No trade execution. BEAR = cash by design.'}
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
          {authUser?.role === 'admin' ? (
            <button type="button" className="btn ghost" onClick={() => setAdminOpen(true)}>
              Admin
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
          {desk === 'mcx' && (
            <>
              <p className="eyebrow">Commodities · MCX majors via global futures</p>
              <h1 className="hero__title">MCX desk</h1>
              <p className="hero__sub">
                Gold, Silver, Crude, NatGas, Copper directional tape with USDINR context.
                Map to the front-month MCX contract and lot size yourself.
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
                    'Demo prices',
                    'Synthetic seed data — not live market prices. Click Force full with Kotak ready to load real EOD.',
                  )
                }
              >
                DEMO — not live
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
            {dataStatus?.latest_date && (
              <button
                type="button"
                className={`meta-chip meta-chip--btn ${chipInfo?.id === 'eod' ? 'is-active' : ''}`}
                onClick={() =>
                  explainChip(
                    'eod',
                    `EOD ${dataStatus.latest_date} · ${dataStatus.status || '—'}`,
                    dataStatus.message ||
                      `Latest local candle date is ${dataStatus.latest_date}. FRESH means recent enough for the desk; STALE means Refresh / Force full first.`,
                  )
                }
              >
                EOD {dataStatus.latest_date}
                {dataStatus.status ? ` · ${dataStatus.status}` : ''}
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
          <div className="banner warn">
            Synthetic demo prices on screen. Run <em>Force full</em> with Kotak for live EOD.
          </div>
        )}

        {isStale && !loading && !isDemo && (
          <div className="banner warn">Price data is stale. Refresh before acting.</div>
        )}

        {!loading && regime && !regime.allow_trading && (
          <div className="banner cash-banner">
            <strong>Cash week — {regime.regime?.replace('_', ' ')}</strong>
            <p>
              {picks?.message || regime.reason} This is intentional risk control, not a
              broken feed — switch to <em>Intraday</em> or <em>MCX</em> for live desks, or
              study the momentum radar below.
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
          <div className="banner info">
            {picks?.message || 'No setups meet criteria — stay in cash.'}
          </div>
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
        {desk === 'mcx' && <McxDesk onAnalyze={onAnalyzeSignal} />}
      </main>

      {desk === 'swing' && (
      <div className="desk__below">
        {swingCalls && (swingCalls.signals || swingCalls.calls)?.length > 0 && (
          <section className="section consultant-swing" id="section-consultant-swing">
            <SignalBoard
              title="Weekly consultant calls"
              subtitle="BUY / SELL / HOLD from the consultant desk — research math, not tips."
              signals={swingCalls.signals || swingCalls.calls}
              source={swingCalls._source || 'consultant'}
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

      {(desk === 'intraday' || desk === 'mcx') && (
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
