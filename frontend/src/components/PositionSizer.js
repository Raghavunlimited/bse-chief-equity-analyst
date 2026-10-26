import React, { useState } from 'react';
import { deskAPI } from '../services/api';

const DEFAULTS = {
  capital: 500000,
  risk_pct: 1,
  entry: '',
  stop: '',
  direction: 'LONG',
  instrument_kind: 'EQ',
  symbol: '',
  lot_size: '',
  multiplier: '1',
  lot_size_verified: true,
  contract_mapping_verified: true,
  expiry: '',
  fixed_costs: 0,
  cost_per_unit: 0,
  cost_per_lot: 0,
  round_trip_cost_pct: 0,
  max_position_pct: '',
  max_lots: '',
  margin_per_lot: '',
  margin_verified: false,
  option_premium: '',
  quote_stale: false,
};

function numOrUndef(v) {
  if (v === '' || v == null) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export default function PositionSizer() {
  const [draft, setDraft] = useState({ ...DEFAULTS });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const setField = (key, val) => setDraft((d) => ({ ...d, [key]: val }));

  const calculate = async (e) => {
    e?.preventDefault?.();
    setBusy(true);
    setError(null);
    try {
      const body = {
        capital: Number(draft.capital),
        risk_pct: Number(draft.risk_pct),
        entry: Number(draft.entry),
        stop: numOrUndef(draft.stop),
        direction: draft.direction,
        instrument_kind: draft.instrument_kind,
        symbol: draft.symbol || undefined,
        lot_size: numOrUndef(draft.lot_size),
        multiplier: numOrUndef(draft.multiplier),
        lot_size_verified: Boolean(draft.lot_size_verified),
        contract_mapping_verified: Boolean(draft.contract_mapping_verified),
        contract_source: 'user_ui',
        expiry: draft.expiry || undefined,
        fixed_costs: Number(draft.fixed_costs) || 0,
        cost_per_unit: Number(draft.cost_per_unit) || 0,
        cost_per_lot: Number(draft.cost_per_lot) || 0,
        round_trip_cost_pct: Number(draft.round_trip_cost_pct) || 0,
        max_position_pct: numOrUndef(draft.max_position_pct),
        max_lots: numOrUndef(draft.max_lots),
        margin_per_lot: numOrUndef(draft.margin_per_lot),
        margin_verified: Boolean(draft.margin_verified),
        option_premium: numOrUndef(draft.option_premium),
        quote_stale: Boolean(draft.quote_stale),
      };
      const res = await deskAPI.calculatePositionSize(body);
      setResult(res.data);
    } catch (err) {
      setResult(null);
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  const size = result?.size;
  const available = result?.available === true;

  return (
    <section
      className="section position-sizer"
      id="section-position-sizer"
      data-testid="position-sizer"
    >
      <div className="section__head">
        <div>
          <h3>Risk position size</h3>
          <p className="section-sub">
            Research calculation from your risk %, entry, stop, costs, and verified
            lot / multiplier. Not an order instruction — does not place trades.
          </p>
        </div>
      </div>

      <p className="banner warn" role="note" data-testid="sizing-disclaimer">
        {result?.disclaimer ||
          'Research calculation only — not an order instruction and does not place trades.'}
      </p>

      <form className="position-sizer__form" onSubmit={calculate}>
        <label>
          <span>Capital (₹)</span>
          <input
            type="number"
            min={1}
            value={draft.capital}
            onChange={(e) => setField('capital', e.target.value)}
            data-testid="sizing-capital"
          />
        </label>
        <label>
          <span>Risk %</span>
          <input
            type="number"
            min={0.01}
            step={0.1}
            value={draft.risk_pct}
            onChange={(e) => setField('risk_pct', e.target.value)}
          />
        </label>
        <label>
          <span>Kind</span>
          <select
            value={draft.instrument_kind}
            onChange={(e) => setField('instrument_kind', e.target.value)}
            data-testid="sizing-kind"
          >
            <option value="EQ">EQ cash</option>
            <option value="FUT">Futures</option>
            <option value="OPT">Options</option>
            <option value="MCX_PROXY">MCX proxy (unavailable)</option>
          </select>
        </label>
        <label>
          <span>Direction</span>
          <select
            value={draft.direction}
            onChange={(e) => setField('direction', e.target.value)}
          >
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </label>
        <label>
          <span>Entry / premium</span>
          <input
            type="number"
            min={0}
            step="any"
            value={draft.entry}
            onChange={(e) => setField('entry', e.target.value)}
            required
            data-testid="sizing-entry"
          />
        </label>
        <label>
          <span>Stop</span>
          <input
            type="number"
            min={0}
            step="any"
            value={draft.stop}
            onChange={(e) => setField('stop', e.target.value)}
            data-testid="sizing-stop"
          />
        </label>
        <label>
          <span>Lot size</span>
          <input
            type="number"
            min={1}
            value={draft.lot_size}
            onChange={(e) => setField('lot_size', e.target.value)}
            placeholder={draft.instrument_kind === 'EQ' ? '1 default' : 'required'}
          />
        </label>
        <label>
          <span>Multiplier</span>
          <input
            type="number"
            min={0}
            step="any"
            value={draft.multiplier}
            onChange={(e) => setField('multiplier', e.target.value)}
          />
        </label>
        <label>
          <span>Fixed costs (₹)</span>
          <input
            type="number"
            min={0}
            value={draft.fixed_costs}
            onChange={(e) => setField('fixed_costs', e.target.value)}
          />
        </label>
        <label>
          <span>Cost / unit</span>
          <input
            type="number"
            min={0}
            step="any"
            value={draft.cost_per_unit}
            onChange={(e) => setField('cost_per_unit', e.target.value)}
          />
        </label>
        <label>
          <span>Max position %</span>
          <input
            type="number"
            min={0}
            value={draft.max_position_pct}
            onChange={(e) => setField('max_position_pct', e.target.value)}
            placeholder="optional"
          />
        </label>
        <label>
          <span>Margin / lot (FUT/short OPT)</span>
          <input
            type="number"
            min={0}
            value={draft.margin_per_lot}
            onChange={(e) => setField('margin_per_lot', e.target.value)}
          />
        </label>
        <label className="position-sizer__check">
          <input
            type="checkbox"
            checked={draft.contract_mapping_verified}
            onChange={(e) => setField('contract_mapping_verified', e.target.checked)}
            data-testid="sizing-mapping-verified"
          />
          <span>Contract mapping verified</span>
        </label>
        <label className="position-sizer__check">
          <input
            type="checkbox"
            checked={draft.lot_size_verified}
            onChange={(e) => setField('lot_size_verified', e.target.checked)}
          />
          <span>Lot size verified</span>
        </label>
        <label className="position-sizer__check">
          <input
            type="checkbox"
            checked={draft.margin_verified}
            onChange={(e) => setField('margin_verified', e.target.checked)}
          />
          <span>Margin verified</span>
        </label>
        <label className="position-sizer__check">
          <input
            type="checkbox"
            checked={draft.quote_stale}
            onChange={(e) => setField('quote_stale', e.target.checked)}
            data-testid="sizing-stale"
          />
          <span>Mark inputs stale</span>
        </label>
        <div className="position-sizer__actions">
          <button type="submit" className="btn" disabled={busy} data-testid="sizing-submit">
            {busy ? 'Calculating…' : 'Calculate size'}
          </button>
        </div>
      </form>

      {error && (
        <p className="error-text" role="alert">
          {String(error)}
        </p>
      )}

      {result && (
        <div className="position-sizer__result" data-testid="sizing-result">
          {!available && (
            <div data-testid="sizing-unavailable">
              <p className="banner warn">
                Size unavailable — no fabricated figure shown.
              </p>
              <ul>
                {(result.blockers || []).map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          )}
          {available && size && (
            <div className="position-sizer__stats" data-testid="sizing-available">
              <div className="oc-stat">
                <span>Lots</span>
                <strong>{size.lots}</strong>
              </div>
              <div className="oc-stat">
                <span>Units</span>
                <strong>{size.units}</strong>
              </div>
              <div className="oc-stat">
                <span>Notional</span>
                <strong>
                  ₹{Number(size.notional).toLocaleString('en-IN')}
                </strong>
              </div>
              <div className="oc-stat">
                <span>Risk ₹</span>
                <strong>
                  ₹{Number(size.risk_rs).toLocaleString('en-IN')}
                </strong>
              </div>
            </div>
          )}
          <div className="position-sizer__explain" data-testid="sizing-formula">
            <h4>Formula</h4>
            <p>{result.formula}</p>
            {result.formula_detail ? <p className="muted">{result.formula_detail}</p> : null}
            <h4>Assumptions</h4>
            <ul>
              {(result.assumptions || []).map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
