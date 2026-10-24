import React, { useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'swing_desk_capital';

const DEFAULTS = {
  capital: 500000,
  riskPct: 1,
  maxPositions: 3,
  reservedCashPct: 20,
  entryStyle: 'breakout',
  targetGainPct: 3,
};

const TARGET_PRESETS = [1, 2, 3, 5, 8];
const CAPITAL_PRESETS = [100000, 250000, 500000, 1000000];

export function loadCapitalSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULTS };
  }
}

function fmtInr(n) {
  return Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

export default function CapitalDesk({ value, onChange, goalPlan, weekLabel }) {
  const [draft, setDraft] = useState(value || loadCapitalSettings());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (value) setDraft(value);
  }, [value]);

  const derived = useMemo(() => {
    const capital = Number(draft.capital) || 0;
    const riskPct = Number(draft.riskPct) || 0;
    const reserved = Number(draft.reservedCashPct) || 0;
    const maxPositions = Number(draft.maxPositions) || 1;
    const targetGainPct = Number(draft.targetGainPct) || 0;
    const riskRupees = capital * (riskPct / 100);
    const deployable = capital * (1 - reserved / 100);
    const targetRupees = capital * (targetGainPct / 100);
    return {
      riskRupees,
      deployable,
      maxRiskBook: riskRupees * maxPositions,
      targetRupees,
    };
  }, [draft]);

  const setField = (key, val) => {
    setDraft((d) => ({ ...d, [key]: val }));
  };

  const apply = () => {
    const next = {
      capital: Math.max(10000, Number(draft.capital) || DEFAULTS.capital),
      riskPct: Math.min(2, Math.max(0.5, Number(draft.riskPct) || 1)),
      maxPositions: Math.min(5, Math.max(1, Number(draft.maxPositions) || 3)),
      reservedCashPct: Math.min(50, Math.max(0, Number(draft.reservedCashPct) || 0)),
      entryStyle: draft.entryStyle === 'pullback' ? 'pullback' : 'breakout',
      targetGainPct: Math.min(
        15,
        Math.max(0.5, Number(draft.targetGainPct) || DEFAULTS.targetGainPct),
      ),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setDraft(next);
    setBusy(true);
    onChange?.(next);
    window.setTimeout(() => setBusy(false), 900);
  };

  const gp = goalPlan || {};
  const reachable = gp.reachable === true;
  const unreachable = gp.reachable === false;
  const plannedReward =
    gp.combined_theoretical_reward_rs ?? gp.combined_potential_rs;
  const week = weekLabel || gp.week_label;

  return (
    <section className="section capital-desk" id="section-capital">
      <div className="section__head capital-desk__head">
        <div>
          <h3>Week Planner</h3>
          <p className="section-sub">
            Tell the desk your capital and the weekly % you want to chase. We size risk,
            check if the screen can even approach that goal, and rank this week&apos;s
            stocks — research math, not a promise.
          </p>
        </div>
        {week ? (
          <div className="week-badge" title="ISO trading week">
            {week}
          </div>
        ) : null}
      </div>

      <div className="capital-desk__presets" role="group" aria-label="Quick capital">
        <span className="capital-desk__presets-label">Capital</span>
        {CAPITAL_PRESETS.map((c) => (
          <button
            key={c}
            type="button"
            className={`chip-btn ${Number(draft.capital) === c ? 'is-on' : ''}`}
            onClick={() => setField('capital', c)}
          >
            ₹{(c / 100000).toFixed(c >= 1000000 ? 0 : 1)}L
          </button>
        ))}
      </div>

      <div className="capital-desk__presets" role="group" aria-label="Target gain presets">
        <span className="capital-desk__presets-label">Target %</span>
        {TARGET_PRESETS.map((t) => (
          <button
            key={t}
            type="button"
            className={`chip-btn ${Number(draft.targetGainPct) === t ? 'is-on' : ''}`}
            onClick={() => setField('targetGainPct', t)}
          >
            {t}%
          </button>
        ))}
      </div>

      <div className="capital-desk__grid">
        <label className="capital-desk__field">
          <span>Trading capital (₹)</span>
          <input
            type="number"
            min={10000}
            step={10000}
            value={draft.capital}
            onChange={(e) => setField('capital', e.target.value)}
          />
        </label>
        <label className="capital-desk__field">
          <span>Target weekly gain (%)</span>
          <input
            type="number"
            min={0.5}
            max={15}
            step={0.5}
            value={draft.targetGainPct}
            onChange={(e) => setField('targetGainPct', e.target.value)}
          />
        </label>
        <label className="capital-desk__field">
          <span>Risk per trade (%)</span>
          <select
            value={draft.riskPct}
            onChange={(e) => setField('riskPct', Number(e.target.value))}
          >
            {[0.5, 1, 1.5, 2].map((v) => (
              <option key={v} value={v}>
                {v}%
              </option>
            ))}
          </select>
        </label>
        <label className="capital-desk__field">
          <span>Max open positions</span>
          <select
            value={draft.maxPositions}
            onChange={(e) => setField('maxPositions', Number(e.target.value))}
          >
            {[1, 2, 3, 4, 5].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="capital-desk__field">
          <span>Reserved cash (%)</span>
          <input
            type="number"
            min={0}
            max={50}
            step={5}
            value={draft.reservedCashPct}
            onChange={(e) => setField('reservedCashPct', e.target.value)}
          />
        </label>
        <label className="capital-desk__field">
          <span>Entry style</span>
          <select
            value={draft.entryStyle}
            onChange={(e) => setField('entryStyle', e.target.value)}
          >
            <option value="breakout">Breakout (near 20D high)</option>
            <option value="pullback">Trend pullback (Stage-2)</option>
          </select>
        </label>
        <div className="capital-desk__apply">
          <button type="button" className="btn primary capital-desk__cta" onClick={apply}>
            {busy ? 'Building plan…' : 'Build this week’s plan'}
          </button>
          <p className="capital-desk__cta-hint">
            Live preview → target ₹{fmtInr(derived.targetRupees)} · risk ₹
            {fmtInr(derived.riskRupees)} / trade
          </p>
        </div>
      </div>

      <div className="stat-grid compact capital-desk__stats">
        <div>
          <span>Risk / trade</span>
          <strong>₹{fmtInr(derived.riskRupees)}</strong>
        </div>
        <div>
          <span>Deployable</span>
          <strong>₹{fmtInr(derived.deployable)}</strong>
        </div>
        <div>
          <span>Max risk book</span>
          <strong>₹{fmtInr(derived.maxRiskBook)}</strong>
        </div>
        <div>
          <span>Style</span>
          <strong>{draft.entryStyle === 'pullback' ? 'Pullback' : 'Breakout'}</strong>
        </div>
      </div>

      {gp && (gp.target_rupees != null || gp.message) && (
        <div
          className={`goal-strip ${
            reachable ? 'goal-strip--yes' : unreachable ? 'goal-strip--no' : ''
          }`}
          role="status"
        >
          <div className="goal-strip__stats">
            <div>
              <span>Target ₹</span>
              <strong>₹{fmtInr(gp.target_rupees ?? derived.targetRupees)}</strong>
            </div>
            <div>
              <span>Reachable</span>
              <strong className={reachable ? 'pos' : unreachable ? 'neg' : ''}>
                {reachable ? 'Yes' : unreachable ? 'No' : '—'}
              </strong>
            </div>
            <div>
              <span>Need ~</span>
              <strong>
                {gp.required_R != null ? `${Number(gp.required_R).toFixed(1)}R` : '—'}
              </strong>
            </div>
            <div>
              <span>Book potential</span>
              <strong>
                {plannedReward != null ? `₹${fmtInr(plannedReward)}` : '—'}
              </strong>
            </div>
          </div>
          {gp.message && <p className="goal-strip__msg">{gp.message}</p>}
        </div>
      )}

      <p className="muted capital-desk__disclaimer">
        Educational research tool — past performance does not guarantee future returns.
        Never risk money you cannot afford to lose.
      </p>
    </section>
  );
}
