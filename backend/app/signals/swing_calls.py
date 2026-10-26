"""
Weekly swing consultant calls — BUY / HOLD (SELL rare).

Cash / blocked-regime weeks emit a HOLD on NIFTY (index) rather than forcing
equity entries. Confidence blends candidate score with regime quality.
"""
from __future__ import annotations

from typing import Any, Optional

from app.config import config
from app.goal_planner import iso_week_label
from app.meta import data_provenance
from app.signals.consultant_rules import grade_swing, weekly_brief
from app.signals.enrichment import attach_enrichment
from app.signals.models import DISCLAIMER, make_call
from app.store import Database
from app.strategy.weekly_swing import check_market_regime, generate_weekly_picks
from universe import SECTOR_MAP

SWING_DISCLAIMER = (
    "Weekly swing research candidates only — not investment advice. "
    "Cash weeks are intentional when NIFTY regime blocks new entries. "
    "No return guarantee; size risk yourself."
)


def _hold_index_call(
    *,
    as_of: str | None,
    regime: dict[str, Any],
    reason: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    g = grade_swing(None, regime)
    thesis = reason or g.get("reason") or "Stay in cash — no new swing entries"
    merged_tags = list(dict.fromkeys([*(tags or []), *(g.get("tags") or []), "CASH_WEEK", "INDEX_HOLD"]))
    return make_call(
        desk="swing",
        symbol="NIFTY",
        side="HOLD",
        confidence=max(float(g.get("confidence") or 40), 55.0),
        thesis=thesis,
        entry=regime.get("nifty_close") or regime.get("nifty_price"),
        stop=None,
        targets={},
        tags=merged_tags,
        sources=["weekly_swing", "nifty_regime"],
        horizon="weekly",
        ttl_hours=24 * 5,
        as_of=as_of,
        disclaimer=SWING_DISCLAIMER,
        extras={"market_regime": regime},
    )


def build_swing_calls(
    *,
    as_of: Optional[str] = None,
    capital: float = 500_000,
    risk_pct: float = 1.0,
    max_positions: int = 3,
    reserved_cash_pct: float = 20.0,
    entry_style: str = "breakout",
    enrich: bool = True,
    enrich_top_n: int = 8,
) -> dict[str, Any]:
    db = Database(config.db_path)
    freshness = db.freshness(config.max_data_age_days)
    provenance = data_provenance(config.db_path)
    as_of_date = as_of or freshness.get("latest_date")
    # as_of week = EOD bar week; calendar week = today (journal / "this week" UI)
    as_of_week = iso_week_label(as_of_date)
    calendar_week = iso_week_label(None)
    week = calendar_week

    nifty = (
        db.get_nifty_series(end_date=as_of_date, lookback=80)
        if as_of_date
        else db.get_nifty_series()
    )
    regime = check_market_regime(nifty)

    if not as_of_date:
        hold = _hold_index_call(
            as_of=None,
            regime=regime,
            reason="No EOD data — run Refresh / Force full before consulting swing desk",
            tags=["NO_DATA"],
        )
        from app.signal_availability import attach_board_availability

        return attach_board_availability(
            {
                "desk": "swing",
                "horizon": "weekly",
                "strategy": "weekly_swing",
                "regime": regime,
                "market_regime": regime,
                "status": "empty",
                "week_label": week,
                "calendar_week_label": calendar_week,
                "as_of_week_label": as_of_week,
                "data_status": freshness,
                "provenance": provenance,
                "as_of": None,
                "calls": [hold],
                "brief": weekly_brief([hold], regime),
                "count": 1,
                "buy_count": 0,
                "hold_count": 1,
                "message": hold["thesis"],
                "disclaimer": SWING_DISCLAIMER,
            }
        )

    snapshot = db.get_joined_snapshot(as_of_date)
    result = generate_weekly_picks(
        snapshot,
        nifty,
        as_of=as_of_date,
        sector_map=SECTOR_MAP,
        top_n=max_positions,
        min_score=config.min_score,
        min_price=config.min_price,
        min_turnover=config.min_traded_value,
        volume_mult=config.volume_multiplier,
        rsi_min=config.rsi_min,
        rsi_max=config.rsi_max,
        rs_min=config.rs_min_outperformance,
        risk_per_trade=risk_pct / 100.0,
        capital_per_trade=capital,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        reserved_cash_pct=reserved_cash_pct,
        entry_style=entry_style,
        require_fresh=True,
        data_status=freshness,
    )

    # Prefer pipeline regime (same snapshot) when present
    regime = result.get("market_regime") or regime
    status = str(result.get("status") or "ok")
    cands = list(result.get("candidates") or [])
    radar = list(result.get("radar") or [])
    calls: list[dict[str, Any]] = []

    cash_week = status in ("cash", "empty", "stale", "error") or not cands or not regime.get(
        "allow_trading", True
    )

    if cash_week:
        calls.append(
            _hold_index_call(
                as_of=as_of_date,
                regime=regime,
                reason=str(result.get("message") or regime.get("reason") or "Cash week"),
                tags=[status.upper(), "CASH_WEEK"],
            )
        )
        # Soft HOLDs on radar (watchlist, not actionable)
        for r in radar[:3]:
            g = grade_swing(r, regime)
            calls.append(
                make_call(
                    desk="swing",
                    symbol=str(r["symbol"]),
                    side="HOLD",
                    confidence=g["confidence"],
                    thesis=(
                        f"Radar watch — not actionable while desk is cash "
                        f"({regime.get('regime')}). {r.get('sector') or ''}"
                    ).strip(),
                    entry=r.get("close") or r.get("entry_price"),
                    tags=list(g.get("tags") or []) + ["RADAR", "NOT_ACTIONABLE"],
                    sources=["weekly_swing_radar"],
                    horizon="weekly",
                    ttl_hours=24 * 5,
                    as_of=as_of_date,
                    disclaimer=SWING_DISCLAIMER,
                    extras={"radar": True, "score": r.get("score")},
                )
            )
    else:
        for c in cands:
            g = grade_swing(c, regime)
            side = g["side"]  # BUY or HOLD; SELL rare on this desk
            calls.append(
                make_call(
                    desk="swing",
                    symbol=c["symbol"],
                    side=side,
                    confidence=g["confidence"],
                    thesis=f"{g['reason']} {c.get('thesis') or ''}".strip(),
                    entry=c.get("entry_price"),
                    stop=c.get("stop_loss"),
                    targets=c.get("targets") if isinstance(c.get("targets"), dict) else {},
                    tags=g.get("tags") or [],
                    sources=["kotak_eod", "india_elite_momentum", "weekly_swing"],
                    horizon="weekly",
                    ttl_hours=24 * 5,
                    as_of=as_of_date,
                    disclaimer=SWING_DISCLAIMER,
                    extras={
                        "score": c.get("score"),
                        "risk_reward": c.get("risk_reward"),
                        "sector": c.get("sector"),
                        "sizing": c.get("sizing"),
                    },
                )
            )

    if enrich and calls:
        # Top N equities only (skip index HOLD) to limit Screener rate
        equity = [c for c in calls if c.get("symbol") not in ("NIFTY", "NIFTY 50")]
        attach_enrichment(
            equity,
            db=db,
            as_of=as_of_date,
            top_n=enrich_top_n,
        )

    from app.expectancy.gate import gate_calls

    calls, exp_regime = gate_calls(
        calls, db=db, desk="swing", as_of=as_of_date, auto_refresh=True
    )

    from app.signal_availability import attach_board_availability

    return attach_board_availability(
        {
            "desk": "swing",
            "horizon": "weekly",
            "strategy": "weekly_swing",
            "regime": regime,
            "market_regime": regime,
            "expectancy_regime": exp_regime,
            "status": status,
            "week_label": week,
            "calendar_week_label": calendar_week,
            "as_of_week_label": as_of_week,
            "data_status": freshness,
            "provenance": provenance,
            "as_of": as_of_date,
            "entry_style": result.get("entry_style"),
            "sizing": result.get("sizing"),
            "radar": radar,
            "calls": calls,
            "brief": weekly_brief(calls, regime),
            "count": len(calls),
            "buy_count": sum(1 for c in calls if c["side"] == "BUY"),
            "sell_count": sum(1 for c in calls if c["side"] == "SELL"),
            "hold_count": sum(1 for c in calls if c["side"] == "HOLD"),
            "message": result.get("message"),
            "disclaimer": SWING_DISCLAIMER or DISCLAIMER,
        }
    )
