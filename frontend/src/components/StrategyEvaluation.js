import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

function fmt(n, d = 2) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
}

export default function StrategyEvaluation() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await deskAPI.getStrategyEvaluation({ run_harness: false });
      setData(res.data);
    } catch (err) {
      setData(null);
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runFresh = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await deskAPI.runStrategyEvaluation({
        run_harness: true,
        oos_fraction: 0.3,
      });
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setRunning(false);
    }
  };

  const evaluations = data?.evaluations || [];
  const bias = data?.bias_checklist || {};
  const baselines = data?.baselines || {};

  return (
    <section
      className="section strategy-eval"
      id="section-strategy-eval"
      data-testid="strategy-eval"
    >
      <div className="section__head">
        <div>
          <h3>Strategy evaluation</h3>
          <p className="section-sub">
            Walk-forward / out-of-sample evidence for audit-confirmed rules only.
            Does not pick a “best” strategy or claim proven future returns.
          </p>
        </div>
        <div className="strategy-eval__actions">
          <button type="button" className="btn ghost" onClick={load} disabled={loading}>
            Refresh stored
          </button>
          <button
            type="button"
            className="btn"
            onClick={runFresh}
            disabled={running}
            data-testid="eval-run"
          >
            {running ? 'Running…' : 'Run walk-forward + OOS'}
          </button>
        </div>
      </div>

      <p className="banner warn" role="note" data-testid="eval-disclaimer">
        {data?.disclaimer ||
          'Research evidence only — not a guarantee or proof of edge.'}
      </p>
      <p className="muted" data-testid="eval-no-best">
        selects_best={String(data?.selects_best ?? false)} · proven=
        {String(data?.proven ?? false)}
      </p>
      {data?.universe_honesty ? (
        <p className="banner warn" role="note" data-testid="eval-universe-honesty">
          {data.universe_honesty}
        </p>
      ) : null}

      {error && (
        <p className="error-text" role="alert">
          {String(error)}
        </p>
      )}
      {loading && !data && <p className="muted">Loading evaluation…</p>}

      {data && (
        <>
          <div className="strategy-eval__period muted" data-testid="eval-period">
            Test period: {data.test_period?.start || '—'} → {data.test_period?.end || '—'} ·
            version {data.strategy_evaluation_version}
          </div>

          <div className="strategy-eval__baselines" data-testid="eval-baselines">
            <h4>Baselines (context only)</h4>
            <p>
              Zero-edge: E={fmt(baselines.zero_edge?.expectancy_r)}R —{' '}
              {baselines.zero_edge?.note}
            </p>
            <p>
              NIFTY buy-hold:{' '}
              {baselines.nifty_buyhold?.available
                ? `${fmt(baselines.nifty_buyhold.return_pct)}% (${baselines.nifty_buyhold.start}→${baselines.nifty_buyhold.end})`
                : baselines.nifty_buyhold?.reason || 'unavailable'}
            </p>
          </div>

          <div className="strategy-eval__bias" data-testid="eval-bias">
            <h4>Bias / validity checklist</h4>
            <ul>
              {Object.entries(bias).map(([k, v]) => (
                <li key={k}>
                  <strong>{k}</strong>: {v.status}
                  {v.residual_risk ? ` — residual: ${v.residual_risk}` : ''}
                </li>
              ))}
            </ul>
          </div>

          <ul className="strategy-eval__list" data-testid="eval-list">
            {evaluations.map((ev) => (
              <li
                key={ev.rule_id}
                className="strategy-eval__item"
                data-testid="eval-row"
                data-rule={ev.rule_id}
                data-evidence={ev.evidence || (ev.available ? 'ok' : 'unavailable')}
              >
                <div className="strategy-eval__item-head">
                  <strong>{ev.meta?.label || ev.label || ev.rule_id}</strong>
                  <span className="chip">{ev.rule_id}</span>
                  <span className="chip muted">{ev.evidence || 'n/a'}</span>
                  {ev.evaluable === false ? (
                    <span className="chip is-down">not evaluable</span>
                  ) : null}
                  {ev.gates?.passes ? (
                    <span className="chip is-up">gates pass (research only)</span>
                  ) : ev.evaluable ? (
                    <span className="chip">gates fail / incomplete</span>
                  ) : null}
                </div>
                {ev.note ? <p className="muted">{ev.note}</p> : null}
                {ev.blockers ? (
                  <p className="muted">Blockers: {(ev.blockers || []).join(', ')}</p>
                ) : null}
                {ev.evaluable !== false && (
                  <div className="strategy-eval__metrics">
                    <span>N={fmt(ev.sample_size, 0)}</span>
                    <span>E={fmt(ev.metrics_all?.expectancy_r)}R</span>
                    <span>PF={fmt(ev.metrics_all?.profit_factor)}</span>
                    <span>DD={fmt(ev.risk?.max_drawdown_pct)}%</span>
                    <span>
                      OOS N=
                      {fmt(ev.out_of_sample?.oos_sample_size, 0)} E=
                      {fmt(ev.out_of_sample?.oos_metrics?.expectancy_r)}R
                    </span>
                  </div>
                )}
                {ev.meta?.timeframe ? (
                  <p className="muted">
                    TF {ev.meta.timeframe} · source {ev.meta.data_source || ev.meta.source || '—'} ·
                    version {ev.meta.strategy_version || '—'}
                  </p>
                ) : null}
                {(ev.limitations || []).length > 0 ? (
                  <ul className="strategy-eval__limits">
                    {(ev.limitations || []).map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>

          <ul className="strategy-eval__limits" data-testid="eval-limitations">
            {(data.limitations || []).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
