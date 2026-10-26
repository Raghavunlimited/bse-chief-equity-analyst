"""
Strategy evaluation — research evidence only.

Evaluates audit-confirmed candidate rules with walk-forward / out-of-sample
splits, India costs, sample-size reporting, regimes, drawdown, and baselines.
Does **not** select a “best” strategy or label results as proven / guaranteed.

Options put/call setups are reported only when required options data **and**
explicit testable entry/invalidation/stop/target/exit rules exist. OI/PCR alone
never produces a directional evaluation signal.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.expectancy.costs import DEFAULT_COSTS, IndiaCostAssumptions
from app.expectancy.gate import STRONG_GATES, _passes_gates
from app.expectancy.harness import (
    RULE_INDEX,
    RULE_INTRADAY,
    RULE_META,
    RULE_SWING,
)
from app.expectancy.metrics import compute_edge_metrics, segment_by_regime
from app.expectancy.persist import ensure_expectancy_schema, list_all_metrics, load_metrics
from app.expectancy.simulate import simulate_trade

DISCLAIMER = (
    "Strategy evaluation is research evidence only — walk-forward / out-of-sample "
    "metrics after stated costs. Results are not a guarantee, proof of edge, or "
    "selection of a 'best' strategy. Insufficient data is labeled explicitly."
)

# Swing walk-forward reads the symbols currently stored for each as_of date.
# There is no point-in-time membership list in this desk.
UNIVERSE_HONESTY = (
    "The swing walk-forward universe is the current stored list, so delisted names are absent."
)

STRATEGY_VERSION = "5.12.0-strategy-eval"

# Audit-confirmed evaluation candidates (desk strategies with harness paths).
CANDIDATE_CATALOG: list[dict[str, Any]] = [
    {
        "rule_id": RULE_SWING,
        "desk": "swing",
        "label": RULE_META[RULE_SWING]["label"],
        "timeframe": "1d",
        "data_source": "sqlite_eod_indicators",
        "harness": "expectancy.harness._run_swing_trades",
        "evaluable_when": "eod_history_ge_60_trading_days",
        "explicit_rules": {
            "entry": "generate_weekly_picks candidate entry_price",
            "invalidation": "stop_loss from ATR/structure rules",
            "stop": "cand.stop_loss",
            "targets": "cand.target_price / targets.t1|t2",
            "exit": "stop | target | time (max_hold days) via simulate_trade",
        },
    },
    {
        "rule_id": RULE_INTRADAY,
        "desk": "intraday",
        "label": RULE_META[RULE_INTRADAY]["label"],
        "timeframe": "5m",
        "data_source": "bars_5m_sqlite",
        "harness": "expectancy.harness_5m.run_intraday_5m_trades",
        "evaluable_when": "sufficient_5m_bars_for_shared_core",
        "explicit_rules": {
            "entry": "intraday_core bias signal on completed 5m bars",
            "invalidation": "stop from core levels",
            "stop": "core stop",
            "targets": "core target",
            "exit": "stop | target | time (max_hold_bars)",
        },
    },
    {
        "rule_id": RULE_INDEX,
        "desk": "index",
        "label": RULE_META[RULE_INDEX]["label"],
        "timeframe": "5m",
        "data_source": "bars_5m_sqlite",
        "harness": "expectancy.harness_5m.run_index_5m_trades",
        "evaluable_when": "sufficient_5m_bars_for_shared_core",
        "explicit_rules": {
            "entry": "index_core MTF/VWAP signal on completed 5m bars",
            "invalidation": "stop from core levels",
            "stop": "core stop",
            "targets": "core target",
            "exit": "stop | target | time (max_hold_bars)",
        },
    },
    {
        "rule_id": "mcx_proxy_bias",
        "desk": "mcx",
        "label": "MCX Yahoo global futures proxy",
        "timeframe": "proxy",
        "data_source": "yahoo_global_futures_usd",
        "harness": None,
        "evaluable_when": None,
        "unavailable_reason": (
            "MCX desk is a USD global-futures proxy without verified INR contract "
            "lots/margins — not in the expectancy harness. Not evaluable as an "
            "exchange strategy."
        ),
        "explicit_rules": None,
    },
    {
        "rule_id": "options_put_call_setup",
        "desk": "options",
        "label": "Put/call options setup (conditional)",
        "timeframe": "options_chain",
        "data_source": "kotak_option_chain_optional",
        "harness": None,
        "evaluable_when": "options_data_and_explicit_testable_rules",
        "unavailable_reason": (
            "No explicit testable put/call entry, invalidation, stop, target, and "
            "exit rules are defined in this codebase. OI/PCR alone must not produce "
            "a directional evaluation signal."
        ),
        "explicit_rules": None,
        "oi_pcr_directional": False,
    },
]


def cost_assumptions_public(
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> dict[str, Any]:
    return {
        "model": "IndiaCostAssumptions",
        "product_paths": ["delivery (swing)", "intraday (index/intraday desks)"],
        "includes_slippage": True,
        "assumptions": asdict(assumptions),
    }


def bias_checklist(*, fill_policy: str = "next_bar_open") -> dict[str, Any]:
    """Structured bias / validity checks — research disclosure, not a clean bill."""
    return {
        "look_ahead_bias": {
            "status": "mitigated_in_harness",
            "detail": (
                f"Signals use bars ≤ as_of; fills use {fill_policy} "
                "(simulate_trade). Same-bar open fills are not used when a next bar exists."
            ),
            "residual_risk": (
                "Intrabar stop-before-target ordering is conservative but path-dependent; "
                "true tick paths are unavailable on EOD/5m bars."
            ),
        },
        "survivorship_bias": {
            "status": "partially_unmitigated",
            "detail": (
                "Universe is current NSE EQ / configured lists. Delisted names are not "
                "reconstructed — historical pick lists may omit failures that left the tape."
            ),
            "residual_risk": "Reported expectancy can be optimistic vs a point-in-time universe.",
        },
        "overfitting": {
            "status": "risk_acknowledged",
            "detail": (
                "Desk parameters (score floors, RSI bands, hold lengths) are conventions, "
                "not cross-validated optima. IS vs OOS divergence is reported when splits run."
            ),
            "residual_risk": "Parameter fishing across regimes remains possible.",
        },
        "multiple_testing": {
            "status": "risk_acknowledged",
            "detail": (
                f"Evaluating {len([c for c in CANDIDATE_CATALOG if c.get('harness')])} "
                "harness-backed rules without crowning a winner. Gate thresholds are fixed "
                "a priori (STRONG_GATES) but still subject to selection effects if operators "
                "cherry-pick regimes."
            ),
            "residual_risk": (
                "No Bonferroni / FDR correction is applied to expectancy comparisons — "
                "do not treat the highest metric as proven."
            ),
            "selects_best": False,
        },
    }


def assert_no_lookahead_fill(bars, *, signal_entry: float, stop: float, target: float) -> dict[str, Any]:
    """
    Quantitative leakage check: with ≥2 bars, entry fill must be bar[1].open,
    not bar[0].close (unless they coincidentally match).
    """
    import pandas as pd

    if bars is None or getattr(bars, "empty", True) or len(bars) < 2:
        return {
            "check": "lookahead_fill",
            "passed": None,
            "reason": "need_ge_2_bars",
        }
    sim = simulate_trade(
        bars,
        signal_entry=signal_entry,
        stop=stop,
        target=target,
        side="BUY",
        max_hold=3,
        product="delivery",
    )
    next_open = float(bars.iloc[1]["open"])
    ok = sim.get("entry_fill") is not None and abs(float(sim["entry_fill"]) - next_open) < 1e-9
    return {
        "check": "lookahead_fill",
        "passed": bool(ok),
        "entry_fill": sim.get("entry_fill"),
        "expected_next_open": next_open,
        "signal_close": float(bars.iloc[0]["close"]),
    }


def split_trades_is_oos(
    trades: list[dict[str, Any]],
    *,
    oos_fraction: float = 0.3,
    date_key: str = "date",
) -> dict[str, Any]:
    """Chronological IS / OOS split by unique signal dates (no shuffling)."""
    if not trades:
        return {
            "in_sample": [],
            "out_of_sample": [],
            "is_metrics": compute_edge_metrics([]),
            "oos_metrics": compute_edge_metrics([]),
            "oos_fraction": oos_fraction,
            "split": "insufficient_trades",
        }
    dates = sorted({str(t.get(date_key) or "") for t in trades if t.get(date_key)})
    if len(dates) < 2:
        return {
            "in_sample": trades,
            "out_of_sample": [],
            "is_metrics": compute_edge_metrics(trades),
            "oos_metrics": compute_edge_metrics([]),
            "oos_fraction": oos_fraction,
            "split": "single_date_no_oos",
            "note": "Cannot form OOS fold with a single signal date — OOS metrics unavailable.",
        }
    n_oos = max(1, int(round(len(dates) * oos_fraction)))
    n_oos = min(n_oos, len(dates) - 1)
    oos_dates = set(dates[-n_oos:])
    is_t = [t for t in trades if str(t.get(date_key) or "") not in oos_dates]
    oos_t = [t for t in trades if str(t.get(date_key) or "") in oos_dates]
    return {
        "in_sample": is_t,
        "out_of_sample": oos_t,
        "is_metrics": compute_edge_metrics(is_t),
        "oos_metrics": compute_edge_metrics(oos_t),
        "oos_fraction": oos_fraction,
        "is_dates": [d for d in dates if d not in oos_dates],
        "oos_dates": sorted(oos_dates),
        "split": "chronological_by_date",
    }


def nifty_buyhold_baseline(
    db,
    *,
    start: Optional[str],
    end: Optional[str],
) -> dict[str, Any]:
    """
    Simple NIFTY buy-and-hold baseline over the test window (gross, no strategy stops).
    Not an R-multiple strategy — provided for context only.
    """
    try:
        nifty = db.get_nifty_series(end_date=end, lookback=800)
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "reason": f"nifty_series_unavailable:{type(e).__name__}",
            "label": "NIFTY buy-hold (context)",
        }
    if nifty is None or getattr(nifty, "empty", True):
        return {
            "available": False,
            "reason": "nifty_series_empty",
            "label": "NIFTY buy-hold (context)",
        }
    df = nifty.copy()
    if "trade_date" in df.columns:
        if start:
            df = df[df["trade_date"] >= start]
        if end:
            df = df[df["trade_date"] <= end]
    if df.empty or len(df) < 2:
        return {
            "available": False,
            "reason": "insufficient_nifty_bars_in_window",
            "label": "NIFTY buy-hold (context)",
        }
    first = float(df.iloc[0]["close"])
    last = float(df.iloc[-1]["close"])
    if first <= 0:
        return {"available": False, "reason": "invalid_nifty_close", "label": "NIFTY buy-hold (context)"}
    ret_pct = (last / first - 1.0) * 100.0
    return {
        "available": True,
        "label": "NIFTY buy-hold (context, gross)",
        "start": str(df.iloc[0]["trade_date"]),
        "end": str(df.iloc[-1]["trade_date"]),
        "return_pct": round(ret_pct, 4),
        "note": (
            "Gross index path — not cost-adjusted strategy R. "
            "Not a claim that beating/losing this baseline proves edge."
        ),
    }


def zero_edge_baseline() -> dict[str, Any]:
    return {
        "available": True,
        "label": "Zero-edge (E=0R) reference",
        "expectancy_r": 0.0,
        "note": "Reference line only — strategies are not ranked against it as winners.",
    }


def options_put_call_evaluation() -> dict[str, Any]:
    """
    Confirm whether options data + explicit testable strategy rules exist.
    Never emits a directional signal from OI/PCR alone.
    """
    chain_available = False
    chain_detail = "not_checked"
    try:
        from app.kotak.option_chain import get_option_chain_hub

        hub = get_option_chain_hub()
        st = hub.status() if hasattr(hub, "status") else {}
        chain_available = bool(st.get("active") or st.get("activated"))
        chain_detail = "active" if chain_available else "inactive_or_empty"
    except Exception as e:  # noqa: BLE001
        chain_detail = f"unavailable:{type(e).__name__}"

    # Explicit strategy rules for put/call setups are not defined in-repo.
    rules_defined = False
    return {
        "rule_id": "options_put_call_setup",
        "evaluable": False,
        "available": False,
        "options_data_present": chain_available,
        "options_data_detail": chain_detail,
        "explicit_rules_defined": rules_defined,
        "entry_invalidation_stop_targets_exit": None,
        "oi_pcr_directional_signal": False,
        "blockers": [
            "explicit_testable_put_call_rules_missing",
            *([] if chain_available else ["options_chain_inactive_or_unavailable"]),
        ],
        "note": (
            "Put/call evaluation withheld. OI/PCR are descriptive only and must not "
            "be treated as a directional strategy signal. Report triggers/stops only "
            "when rules are explicitly defined and testable."
        ),
        "proven": False,
    }


def _evidence_label(metrics: dict[str, Any] | None) -> str:
    if not metrics or int(metrics.get("sample_size") or 0) == 0:
        return "insufficient_data"
    passes, _ = _passes_gates({**metrics, "meta": {}})
    if passes:
        return "gate_pass_research_only"
    return "evidence_below_gates"


def evaluate_trades_bundle(
    trades: list[dict[str, Any]],
    *,
    rule_id: str,
    meta: dict[str, Any],
    oos_fraction: float = 0.3,
) -> dict[str, Any]:
    by_regime = segment_by_regime(trades)
    overall = by_regime.get("ALL") or compute_edge_metrics(trades)
    split = split_trades_is_oos(trades, oos_fraction=oos_fraction)
    n = int(overall.get("sample_size") or 0)
    passes, fails = _passes_gates({**overall, "meta": meta, "rule_id": rule_id})
    evidence = _evidence_label(overall)
    return {
        "rule_id": rule_id,
        "evaluable": True,
        "available": n > 0,
        "evidence": evidence,
        "proven": False,
        "best": False,
        "sample_size": n,
        "metrics_all": overall,
        "by_regime": by_regime,
        "walk_forward": {
            "trade_count": len(trades),
            "note": "Event-driven walk-forward trades (same harness as expectancy).",
        },
        "out_of_sample": {
            "split": split.get("split"),
            "oos_fraction": split.get("oos_fraction"),
            "is_metrics": split.get("is_metrics"),
            "oos_metrics": split.get("oos_metrics"),
            "is_sample_size": (split.get("is_metrics") or {}).get("sample_size"),
            "oos_sample_size": (split.get("oos_metrics") or {}).get("sample_size"),
            "note": split.get("note"),
        },
        "risk": {
            "max_drawdown_pct": overall.get("max_drawdown_pct"),
            "profit_factor": overall.get("profit_factor"),
            "expectancy_r": overall.get("expectancy_r"),
        },
        "gates": {
            **STRONG_GATES,
            "passes": passes,
            "fails": fails,
        },
        "meta": meta,
        "limitations": [
            "Not a profit guarantee or proven edge.",
            "Survivorship and parameter risks remain (see bias_checklist).",
            *(
                ["Insufficient sample — do not treat metrics as actionable evidence."]
                if evidence == "insufficient_data"
                else []
            ),
        ],
    }


def audit_availability(db) -> dict[str, Any]:
    """What the audit confirms is available for evaluation right now."""
    dates = []
    try:
        dates = db.get_trading_dates() or []
    except Exception:  # noqa: BLE001
        dates = []
    bars_5m = {}
    try:
        from app.bars_5m import bar_counts

        bars_5m = bar_counts() or {}
    except Exception:  # noqa: BLE001
        bars_5m = {"error": "bars_5m_unavailable"}

    eod_ok = len(dates) >= 60
    bars_completed = int(bars_5m.get("completed_bars") or bars_5m.get("bars") or 0)
    # harness_5m has its own sufficiency checks; surface raw counts here
    five_m_ok = bars_completed >= 50  # soft preview; harness may still say insufficient

    candidates = []
    for c in CANDIDATE_CATALOG:
        rid = c["rule_id"]
        if rid == RULE_SWING:
            avail = eod_ok
            reason = None if avail else "Need ≥60 EOD trading days"
        elif rid in (RULE_INTRADAY, RULE_INDEX):
            avail = five_m_ok
            reason = None if avail else "Insufficient completed 5m bars (harness may still refuse)"
        elif rid == "mcx_proxy_bias":
            avail = False
            reason = c.get("unavailable_reason")
        elif rid == "options_put_call_setup":
            opt = options_put_call_evaluation()
            avail = False
            reason = opt.get("note")
        else:
            avail = False
            reason = "unknown_candidate"
        candidates.append(
            {
                **{k: c[k] for k in (
                    "rule_id", "desk", "label", "timeframe", "data_source", "harness"
                ) if k in c},
                "available_for_evaluation": avail,
                "unavailable_reason": reason,
                "explicit_rules": c.get("explicit_rules"),
                "oi_pcr_directional": c.get("oi_pcr_directional", False),
            }
        )
    return {
        "eod_trading_days": len(dates),
        "eod_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
        "bars_5m": bars_5m,
        "candidates": candidates,
        "selects_best": False,
    }


def build_evaluation_report(
    db,
    *,
    rules: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    oos_fraction: float = 0.3,
    run_harness: bool = True,
    sector_map: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    Full evaluation report. Never marks a winner.
    If run_harness=False, assemble from stored expectancy metrics only.
    """
    ensure_expectancy_schema(db)
    audit = audit_availability(db)
    wanted = rules or [RULE_SWING, RULE_INTRADAY, RULE_INDEX]
    evaluations: list[dict[str, Any]] = []
    harness_result: dict[str, Any] | None = None

    if run_harness:
        from app.config import config
        from app.expectancy.harness import _run_swing_trades

        if sector_map is None:
            try:
                from universe import SECTOR_MAP

                sector_map = SECTOR_MAP
            except Exception:  # noqa: BLE001
                sector_map = {}

        dates = db.get_trading_dates(end_date=end_date) or []
        if start_date:
            dates = [d for d in dates if d >= start_date]
        harness_result = {
            "status": "ok" if len(dates) >= 60 else "error",
            "message": (
                f"Evaluation walk-forward on {len(dates)} sessions"
                if len(dates) >= 60
                else "Need ≥60 trading days of OHLCV history"
            ),
            "date_start": dates[0] if dates else None,
            "date_end": dates[-1] if dates else None,
        }

        swing_kwargs = {
            "top_n": getattr(config, "top_n", 2),
            "min_score": getattr(config, "min_score", 65),
            "min_price": getattr(config, "min_price", 100),
            "min_turnover": getattr(config, "min_traded_value", 10_00_00_000),
            "volume_mult": getattr(config, "volume_multiplier", 2.0),
            "rsi_min": getattr(config, "rsi_min", 45),
            "rsi_max": getattr(config, "rsi_max", 70),
            "rs_min": getattr(config, "rs_min_outperformance", 3.0),
            "risk_per_trade": getattr(config, "risk_per_trade", 0.02),
        }

        for rid in wanted:
            if rid not in (RULE_SWING, RULE_INTRADAY, RULE_INDEX):
                continue
            tlist: list[dict[str, Any]] = []
            payload: dict[str, Any] = {}
            if rid == RULE_SWING:
                if len(dates) < 60:
                    payload = {"insufficient_history": True, "trade_count": 0}
                else:
                    tlist = _run_swing_trades(
                        db,
                        sector_map=sector_map,
                        dates=dates,
                        config_kwargs=swing_kwargs,
                    )
                    payload = {"trade_count": len(tlist)}
            elif rid == RULE_INDEX:
                from app.expectancy.harness_5m import run_index_5m_trades

                tlist, payload = run_index_5m_trades(db)
            else:
                from app.expectancy.harness_5m import run_intraday_5m_trades

                tlist, payload = run_intraday_5m_trades(db)

            meta = {
                **RULE_META.get(rid, {}),
                **payload,
                "strategy_version": STRATEGY_VERSION,
                "strategy_id": rid,
                "data_interval": payload.get("data_interval")
                or RULE_META.get(rid, {}).get("data_interval"),
                "timeframe": payload.get("timeframe")
                or RULE_META.get(rid, {}).get("timeframe"),
                "proxy": bool(payload.get("proxy")),
                "insufficient_history": bool(payload.get("insufficient_history")),
                "cost_assumptions": cost_assumptions_public(),
                "test_period": {
                    "start": harness_result.get("date_start"),
                    "end": harness_result.get("date_end"),
                },
                "parameters": {
                    "note": "Desk config conventions — not cross-validated optima.",
                    "max_hold": RULE_META.get(rid, {}).get("max_hold")
                    or RULE_META.get(rid, {}).get("max_hold_bars"),
                },
                "assumptions": [
                    "India round-trip costs + slippage via IndiaCostAssumptions",
                    "Next-bar open fill (no same-bar lookahead when next bar exists)",
                    "Regime labels from expectancy.regimes.regime_at (bars ≤ as_of)",
                ],
            }
            if not tlist:
                evaluations.append(
                    {
                        "rule_id": rid,
                        "evaluable": True,
                        "available": False,
                        "evidence": "insufficient_data",
                        "proven": False,
                        "best": False,
                        "sample_size": 0,
                        "metrics_all": compute_edge_metrics([]),
                        "by_regime": payload.get("by_regime") or {},
                        "gates": {**STRONG_GATES, "passes": False, "fails": ["N=0"]},
                        "meta": meta,
                        "limitations": [
                            payload.get("honesty")
                            or payload.get("disclaimer")
                            or "Insufficient history / zero trades for walk-forward evaluation."
                        ],
                        "out_of_sample": {
                            "split": "unavailable",
                            "note": "No trades to split.",
                        },
                        "risk": {
                            "max_drawdown_pct": None,
                            "profit_factor": None,
                            "expectancy_r": None,
                        },
                    }
                )
                continue
            evaluations.append(
                evaluate_trades_bundle(
                    tlist, rule_id=rid, meta=meta, oos_fraction=oos_fraction
                )
            )
    else:
        # Stored metrics path — no new walk-forward
        for rid in wanted:
            if rid not in (RULE_SWING, RULE_INTRADAY, RULE_INDEX):
                continue
            m = load_metrics(db, rule_id=rid, regime="ALL")
            meta_json = {}
            if m and m.get("meta_json"):
                try:
                    meta_json = json.loads(m["meta_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    meta_json = {}
            overall = m or compute_edge_metrics([])
            passes, fails = _passes_gates(
                {**(m or {}), "meta": meta_json, "rule_id": rid}
            )
            evaluations.append(
                {
                    "rule_id": rid,
                    "evaluable": True,
                    "available": int((m or {}).get("sample_size") or 0) > 0,
                    "evidence": _evidence_label(m),
                    "proven": False,
                    "best": False,
                    "sample_size": int((m or {}).get("sample_size") or 0),
                    "metrics_all": {
                        k: (m or {}).get(k)
                        for k in (
                            "sample_size",
                            "win_rate_pct",
                            "avg_win_r",
                            "avg_loss_r",
                            "expectancy_r",
                            "profit_factor",
                            "max_drawdown_pct",
                        )
                    },
                    "by_regime": None,
                    "out_of_sample": {
                        "split": "not_run",
                        "note": "Stored metrics view — POST evaluate with run_harness for IS/OOS.",
                    },
                    "gates": {**STRONG_GATES, "passes": passes, "fails": fails},
                    "meta": {
                        **RULE_META.get(rid, {}),
                        **meta_json,
                        "strategy_version": STRATEGY_VERSION,
                        "source": "persisted_expectancy_metrics",
                    },
                    "limitations": [
                        "Persisted metrics only — not a fresh OOS fold.",
                        "Not a guarantee or proof of future returns.",
                    ],
                    "risk": {
                        "max_drawdown_pct": (m or {}).get("max_drawdown_pct"),
                        "profit_factor": (m or {}).get("profit_factor"),
                        "expectancy_r": (m or {}).get("expectancy_r"),
                    },
                }
            )

    # Always append non-evaluable catalog entries when requested / default
    evaluations.append(
        {
            "rule_id": "mcx_proxy_bias",
            "evaluable": False,
            "available": False,
            "evidence": "unavailable",
            "proven": False,
            "best": False,
            "blockers": ["mcx_proxy_not_in_harness"],
            "note": next(
                c["unavailable_reason"]
                for c in CANDIDATE_CATALOG
                if c["rule_id"] == "mcx_proxy_bias"
            ),
        }
    )
    evaluations.append(options_put_call_evaluation())

    period_start = (harness_result or {}).get("date_start") or start_date
    period_end = (harness_result or {}).get("date_end") or end_date or audit["eod_range"].get("end")

    return {
        "status": "ok",
        "strategy_evaluation_version": STRATEGY_VERSION,
        "disclaimer": DISCLAIMER,
        "universe_honesty": UNIVERSE_HONESTY,
        "proven": False,
        "selects_best": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "audit": audit,
        "test_period": {"start": period_start, "end": period_end},
        "cost_model": cost_assumptions_public(),
        "bias_checklist": bias_checklist(),
        "baselines": {
            "zero_edge": zero_edge_baseline(),
            "nifty_buyhold": nifty_buyhold_baseline(db, start=period_start, end=period_end),
        },
        "gates": STRONG_GATES,
        "evaluations": evaluations,
        "harness_status": (harness_result or {}).get("status"),
        "harness_message": (harness_result or {}).get("message"),
        "limitations": [
            "No strategy is labeled best or proven.",
            "Historical gate pass ≠ future returns.",
            "Multiple-testing and survivorship risks are disclosed, not eliminated.",
            "Options put/call setups require explicit testable rules — OI/PCR is not a signal.",
        ],
        "stored_metrics_count": len(list_all_metrics(db)),
    }
