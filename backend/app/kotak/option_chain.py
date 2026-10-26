"""
Live Option Chain Matrix + institutional analytics.

Resolves nearest weekly/monthly expiry, subscribes ATM±N CE/PE via FeedHub,
computes per-strike metrics + Greeks, PCR / Max Pain / walls / straddle,
and Futures + strike OI buildup quadrants.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from app.kotak.feed_hub import FeedHub, get_feed_hub
from app.kotak.greeks import compute_greeks
from app.kotak.oi_buildup import BuildupResult, classify_oi_buildup, max_pain_strike
from app.kotak.scrip_master import Instrument, ScripMaster, get_scrip_master
from app.kotak.session import get_kotak_session
from app.market_types import LiveQuote

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

ExpiryMode = Literal["nearest", "weekly", "monthly"]
DEFAULT_WING = 15
ATM_PCR_WING = 5


def _risk_free() -> float:
    try:
        return float(os.getenv("KOTAK_RISK_FREE_RATE", "0.065"))
    except ValueError:
        return 0.065


def _as_date(v: date | str) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v).strip()[:10])


def pick_expiry(
    underlying: str,
    *,
    mode: ExpiryMode = "nearest",
    exchange_segment: str = "nse_fo",
    as_of: date | None = None,
    scrip: ScripMaster | None = None,
) -> date:
    """
    nearest/weekly → first upcoming option expiry.
    monthly → last expiry falling in the current (or next) calendar month.
    """
    sm = scrip or get_scrip_master()
    today = as_of or datetime.now(IST).date()
    exps = [_as_date(e) for e in sm.list_expiries(underlying, kind="OPT", exchange_segment=exchange_segment)]
    upcoming = [e for e in exps if e >= today]
    if not upcoming:
        raise LookupError(f"No upcoming option expiries for {underlying}")
    if mode in ("nearest", "weekly"):
        return upcoming[0]
    # monthly: prefer last expiry of current month if still listed; else next month's last
    cur_month = [e for e in upcoming if e.year == today.year and e.month == today.month]
    if cur_month:
        return cur_month[-1]
    ym = upcoming[0].year, upcoming[0].month
    month_bucket = [e for e in upcoming if (e.year, e.month) == ym]
    return month_bucket[-1]


def _atm_index(strikes: list[float], spot: float) -> int:
    return min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))


def _t_years(expiry: date, now: Optional[datetime] = None) -> float:
    """Years to expiry — NSE equity derivatives typically settle ~15:30 IST."""
    now = now or datetime.now(IST)
    exp_dt = datetime(expiry.year, expiry.month, expiry.day, 15, 30, tzinfo=IST)
    secs = (exp_dt - now).total_seconds()
    return max(secs / (365.25 * 24 * 3600), 0.0)


@dataclass
class _StrikeLegs:
    strike: float
    ce: Optional[Instrument] = None
    pe: Optional[Instrument] = None


@dataclass
class ChainState:
    underlying: str
    expiry: date
    exchange_segment: str
    wing: int
    spot: float = 0.0
    atm: float = 0.0
    future: Optional[Instrument] = None
    future_key: Optional[str] = None
    legs: list[_StrikeLegs] = field(default_factory=list)
    # key → baseline OI / price at first observation (session)
    oi_baseline: dict[str, float] = field(default_factory=dict)
    price_baseline: dict[str, float] = field(default_factory=dict)
    subscribed_keys: list[str] = field(default_factory=list)
    started_at: float = 0.0


class OptionChainEngine:
    """Process-wide live chain manager (one active chain per underlying)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chains: dict[str, ChainState] = {}
        self._hub: FeedHub = get_feed_hub()

    def status(self, underlying: str | None = None) -> dict[str, Any]:
        with self._lock:
            if underlying:
                st = self._chains.get(underlying.upper())
                if not st:
                    return {"active": False, "underlying": underlying}
                return {
                    "active": True,
                    "underlying": st.underlying,
                    "expiry": st.expiry.isoformat(),
                    "wing": st.wing,
                    "atm": st.atm,
                    "spot": st.spot,
                    "strikes": len(st.legs),
                    "subscribed": len(st.subscribed_keys),
                    "started_at": st.started_at,
                }
            return {
                "active_underlyings": list(self._chains.keys()),
                "session": get_kotak_session().status(),
                "feed": self._hub.status(),
            }

    def activate(
        self,
        underlying: str,
        *,
        expiry: date | str | None = None,
        expiry_mode: ExpiryMode = "nearest",
        wing: int = DEFAULT_WING,
        exchange_segment: str = "nse_fo",
        spot_hint: float | None = None,
    ) -> dict[str, Any]:
        """
        Resolve expiry + ATM±wing, subscribe CE/PE (+ future) on the live feed.
        Fails loud without a Kotak session.
        """
        und = underlying.upper().strip()
        wing = max(1, min(int(wing), 40))
        # Ensure session / WS
        get_kotak_session().require()
        try:
            self._hub.start()
        except Exception as e:
            raise RuntimeError(f"Kotak feed not connected: {e}") from e

        sm = get_scrip_master()
        sm.ensure_loaded()
        exp = _as_date(expiry) if expiry else pick_expiry(
            und, mode=expiry_mode, exchange_segment=exchange_segment, scrip=sm
        )
        chain_all = sm.option_chain_tokens(und, exp, exchange_segment=exchange_segment)
        if not chain_all:
            raise LookupError(f"Empty option chain for {und} {exp}")

        spot = self._resolve_spot(und, spot_hint=spot_hint, exchange_segment=exchange_segment)
        if spot is None or spot <= 0:
            raise RuntimeError(
                f"Cannot determine live underlying LTP for {und}. "
                "Subscribe index/spot first or pass spot_hint."
            )

        strikes = sorted({float(i.strike) for i in chain_all if i.strike is not None})
        if not strikes:
            raise LookupError(f"No strikes for {und} {exp}")
        atm_i = _atm_index(strikes, spot)
        lo = max(0, atm_i - wing)
        hi = min(len(strikes) - 1, atm_i + wing)
        selected = strikes[lo : hi + 1]
        atm = strikes[atm_i]

        by_strike: dict[float, _StrikeLegs] = {k: _StrikeLegs(strike=k) for k in selected}
        for inst in chain_all:
            if inst.strike is None or inst.strike not in by_strike:
                continue
            if inst.option_right == "CE":
                by_strike[inst.strike].ce = inst
            elif inst.option_right == "PE":
                by_strike[inst.strike].pe = inst

        legs = [by_strike[k] for k in selected]
        instruments: list[Instrument] = []
        for leg in legs:
            if leg.ce:
                instruments.append(leg.ce)
            if leg.pe:
                instruments.append(leg.pe)

        fut: Optional[Instrument] = None
        try:
            fut = sm.nearest_future(und, exchange_segment=exchange_segment)
            instruments.append(fut)
        except LookupError:
            fut = None

        keys = self._hub.subscribe_instruments(instruments, with_depth=True, with_touch=True)
        # Also try to keep index/spot flowing for NIFTY/BANKNIFTY via yahoo alias path
        self._ensure_underlying_alias(und)

        state = ChainState(
            underlying=und,
            expiry=exp,
            exchange_segment=exchange_segment,
            wing=wing,
            spot=spot,
            atm=atm,
            future=fut,
            future_key=f"{fut.exchange_segment}|{fut.instrument_token}" if fut else None,
            legs=legs,
            subscribed_keys=keys,
            started_at=time.time(),
        )
        with self._lock:
            old = self._chains.get(und)
            if old and old.subscribed_keys:
                # Keep overlapping; unsubscribe only keys no longer needed
                drop = [k for k in old.subscribed_keys if k not in set(keys)]
                if drop:
                    try:
                        self._hub.unsubscribe(drop)
                    except Exception as e:
                        logger.warning("unsubscribe old chain legs: %s", e)
            self._chains[und] = state

        return self.snapshot(und)

    def snapshot(self, underlying: str) -> dict[str, Any]:
        und = underlying.upper().strip()
        with self._lock:
            st = self._chains.get(und)
            if st is None:
                raise LookupError(
                    f"No active option chain for {und}. "
                    "POST /api/kotak/option-chain/activate first."
                )
            # copy refs under lock
            state = st

        spot = self._resolve_spot(und, spot_hint=state.spot, exchange_segment=state.exchange_segment)
        if spot and spot > 0:
            state.spot = spot

        t_yrs = _t_years(state.expiry)
        r = _risk_free()
        rows: list[dict[str, Any]] = []
        call_oi: dict[float, float] = {}
        put_oi: dict[float, float] = {}
        call_vol = 0.0
        put_vol = 0.0
        call_oi_add: dict[float, float] = {}
        put_oi_add: dict[float, float] = {}

        for leg in state.legs:
            ce_side = self._leg_metrics(
                state, leg.ce, "CE", state.spot, t_yrs, r
            ) if leg.ce else None
            pe_side = self._leg_metrics(
                state, leg.pe, "PE", state.spot, t_yrs, r
            ) if leg.pe else None
            if ce_side and ce_side.get("oi") is not None:
                call_oi[leg.strike] = float(ce_side["oi"])
                call_oi_add[leg.strike] = float(ce_side.get("oi_change") or 0.0)
                call_vol += float(ce_side.get("volume") or 0.0)
            if pe_side and pe_side.get("oi") is not None:
                put_oi[leg.strike] = float(pe_side["oi"])
                put_oi_add[leg.strike] = float(pe_side.get("oi_change") or 0.0)
                put_vol += float(pe_side.get("volume") or 0.0)

            itm_ce = state.spot > leg.strike
            itm_pe = state.spot < leg.strike
            rows.append(
                {
                    "strike": leg.strike,
                    "atm": abs(leg.strike - state.atm) < 1e-9,
                    "ce": ce_side,
                    "pe": pe_side,
                    "ce_itm": itm_ce,
                    "pe_itm": itm_pe,
                }
            )

        analytics = self._analytics(
            state=state,
            rows=rows,
            call_oi=call_oi,
            put_oi=put_oi,
            call_oi_add=call_oi_add,
            put_oi_add=put_oi_add,
            call_vol=call_vol,
            put_vol=put_vol,
        )
        fut_buildup = self._future_buildup(state)

        return {
            "underlying": und,
            "expiry": state.expiry.isoformat(),
            "expiry_mode_resolved": state.expiry.isoformat(),
            "exchange_segment": state.exchange_segment,
            "wing": state.wing,
            "spot": state.spot,
            "atm": state.atm,
            "t_years": round(t_yrs, 6),
            "risk_free_rate": r,
            "future": {
                "trading_symbol": state.future.trading_symbol if state.future else None,
                "instrument_token": state.future.instrument_token if state.future else None,
                "key": state.future_key,
                "buildup": fut_buildup.to_dict() if fut_buildup else None,
                "quote": self._quote_dict(state.future_key) if state.future_key else None,
            },
            "rows": rows,
            "analytics": analytics,
            "subscribed": len(state.subscribed_keys),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "kotak_neo_ws",
            "demo": False,
        }

    # --- internals -------------------------------------------------------

    def _ensure_underlying_alias(self, und: str) -> None:
        # Feed hub aliases NIFTY/BANKNIFTY from index ticks when subscribed by name.
        # Equity underlyings: subscribe cash EQ so spot is live.
        if und in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"):
            return
        try:
            self._hub.subscribe_equity(und, exchange_segment="nse_cm")
        except Exception as e:
            logger.warning("equity spot subscribe %s failed: %s", und, e)

    def _resolve_spot(
        self,
        und: str,
        *,
        spot_hint: float | None,
        exchange_segment: str,
    ) -> Optional[float]:
        # Prefer live quote aliases
        for cand in (und, f"{und}-EQ", "NIFTY 50" if und == "NIFTY" else und,
                     "Nifty Bank" if und == "BANKNIFTY" else und):
            q = self._hub.get_quote(cand)
            if q and q.ltp and q.ltp > 0:
                return float(q.ltp)
        # Yahoo bridge via live_quotes only as last resort for index (still live, not demo)
        if und in ("NIFTY", "BANKNIFTY"):
            try:
                from app import live_quotes

                ysym = "^NSEI" if und == "NIFTY" else "^NSEBANK"
                yq = live_quotes.quote_snapshot(ysym)
                if yq.ltp and yq.ltp > 0 and yq.feed_status != "ERROR":
                    return float(yq.ltp)
            except Exception as e:
                logger.warning("yahoo spot fallback failed: %s", e)
        # Futures LTP as proxy
        try:
            fut = get_scrip_master().nearest_future(und, exchange_segment=exchange_segment)
            fq = self._hub.get_quote(fut.key())
            if fq and fq.ltp and fq.ltp > 0:
                return float(fq.ltp)
        except Exception:
            pass
        return float(spot_hint) if spot_hint and spot_hint > 0 else None

    def _quote_dict(self, key: Optional[str]) -> Optional[dict[str, Any]]:
        if not key:
            return None
        q = self._hub.get_quote(key)
        return q.to_dict() if q else None

    def _baselines(self, state: ChainState, key: str, q: LiveQuote) -> tuple[float, float]:
        """Return (oi_baseline, price_baseline), seeding on first sight."""
        with self._lock:
            if key not in state.oi_baseline and q.oi is not None:
                # Prefer prev_day_oi when feed provides it
                base_oi = float(q.prev_day_oi) if q.prev_day_oi is not None else float(q.oi)
                state.oi_baseline[key] = base_oi
            if key not in state.price_baseline and q.ltp is not None:
                # Prefer prev_close for day price change when available
                base_px = float(q.prev_close) if q.prev_close else float(q.ltp)
                state.price_baseline[key] = base_px
            oi_b = state.oi_baseline.get(key)
            px_b = state.price_baseline.get(key)
        return (
            float(oi_b) if oi_b is not None else float(q.prev_day_oi or q.oi or 0.0),
            float(px_b) if px_b is not None else float(q.prev_close or q.ltp or 0.0),
        )

    def _leg_metrics(
        self,
        state: ChainState,
        inst: Instrument,
        right: str,
        spot: float,
        t_yrs: float,
        r: float,
    ) -> dict[str, Any]:
        key = inst.key()
        q = self._hub.get_quote(key)
        book = self._hub.get_book(key)
        if q is None or q.ltp is None:
            return {
                "instrument_token": inst.instrument_token,
                "trading_symbol": inst.trading_symbol,
                "key": key,
                "ltp": None,
                "net_chg_pct": None,
                "volume": None,
                "oi": None,
                "oi_change": None,
                "bid": None,
                "ask": None,
                "iv": None,
                "delta": None,
                "theta": None,
                "gamma": None,
                "vega": None,
                "buildup": classify_oi_buildup(None, None).to_dict(),
                "feed_status": "ERROR",
                "lot_size": inst.lot_size,
                "tick_size": inst.tick_size,
                "error": "no_live_quote",
            }

        oi_base, px_base = self._baselines(state, key, q)
        oi = float(q.oi) if q.oi is not None else None
        oi_chg = (oi - oi_base) if oi is not None else None
        # Prefer quote change_pct; else vs baseline/prev_close
        net_chg = q.change_pct
        if net_chg is None and q.prev_close and q.prev_close > 0 and q.ltp:
            net_chg = (float(q.ltp) / float(q.prev_close) - 1.0) * 100.0
        price_chg = (float(q.ltp) - px_base) if q.ltp is not None else None

        bid = book.best_bid if book else None
        ask = book.best_ask if book else None
        if bid is None and q.depth_bids:
            bid = q.depth_bids[0].get("price")
        if ask is None and q.depth_asks:
            ask = q.depth_asks[0].get("price")

        g = compute_greeks(
            premium=float(q.ltp),
            spot=spot,
            strike=float(inst.strike or 0),
            t_years=t_yrs,
            right=right,
            underlying=state.underlying,
            r=r,
        )
        buildup = classify_oi_buildup(price_chg, oi_chg)

        return {
            "instrument_token": inst.instrument_token,
            "trading_symbol": inst.trading_symbol,
            "key": key,
            "ltp": float(q.ltp),
            "net_chg_pct": round(float(net_chg), 4) if net_chg is not None else None,
            "volume": float(q.session_volume) if q.session_volume is not None else None,
            "oi": oi,
            "oi_change": oi_chg,
            "prev_day_oi": float(q.prev_day_oi) if q.prev_day_oi is not None else oi_base,
            "bid": bid,
            "ask": ask,
            "spread_pct": q.spread_pct if q.spread_pct is not None else (book.spread_pct if book else None),
            "obi": q.obi if q.obi is not None else (book.obi if book else None),
            "iv": g.iv,
            "iv_pct": round(g.iv * 100.0, 4) if g.iv is not None else None,
            "delta": g.delta,
            "theta": g.theta,
            "gamma": g.gamma,
            "vega": g.vega,
            "greeks_model": g.model,
            "greeks_ok": g.ok,
            "buildup": buildup.to_dict(),
            "feed_status": q.feed_status,
            "lot_size": inst.lot_size,
            "tick_size": inst.tick_size,
            "quote_age_sec": q.age_sec,
        }

    def _future_buildup(self, state: ChainState) -> Optional[BuildupResult]:
        if not state.future_key:
            return None
        q = self._hub.get_quote(state.future_key)
        if q is None or q.ltp is None:
            return classify_oi_buildup(None, None)
        oi_base, px_base = self._baselines(state, state.future_key, q)
        oi = float(q.oi) if q.oi is not None else None
        oi_chg = (oi - oi_base) if oi is not None else None
        price_chg = float(q.ltp) - px_base
        return classify_oi_buildup(price_chg, oi_chg)

    def _analytics(
        self,
        *,
        state: ChainState,
        rows: list[dict[str, Any]],
        call_oi: dict[float, float],
        put_oi: dict[float, float],
        call_oi_add: dict[float, float],
        put_oi_add: dict[float, float],
        call_vol: float,
        put_vol: float,
    ) -> dict[str, Any]:
        tot_ce = sum(call_oi.values())
        tot_pe = sum(put_oi.values())
        total_pcr = (tot_pe / tot_ce) if tot_ce > 0 else None

        # ATM ± 5 strikes PCR
        strikes = [r["strike"] for r in rows]
        if strikes:
            atm_i = _atm_index(strikes, state.spot)
            lo = max(0, atm_i - ATM_PCR_WING)
            hi = min(len(strikes) - 1, atm_i + ATM_PCR_WING)
            band = strikes[lo : hi + 1]
            ce_b = sum(call_oi.get(k, 0.0) for k in band)
            pe_b = sum(put_oi.get(k, 0.0) for k in band)
            atm_pcr = (pe_b / ce_b) if ce_b > 0 else None
        else:
            atm_pcr = None
            band = []

        vol_pcr = (put_vol / call_vol) if call_vol > 0 else None
        pain = max_pain_strike(strikes, call_oi, put_oi)

        call_wall_oi = max(call_oi.items(), key=lambda kv: kv[1])[0] if call_oi else None
        put_wall_oi = max(put_oi.items(), key=lambda kv: kv[1])[0] if put_oi else None
        call_wall_add = (
            max(call_oi_add.items(), key=lambda kv: kv[1])[0] if call_oi_add else None
        )
        put_wall_add = (
            max(put_oi_add.items(), key=lambda kv: kv[1])[0] if put_oi_add else None
        )

        # ATM straddle
        atm_row = next((r for r in rows if r.get("atm")), None)
        ce_ltp = (atm_row or {}).get("ce", {}) or {}
        pe_ltp = (atm_row or {}).get("pe", {}) or {}
        ce_p = ce_ltp.get("ltp")
        pe_p = pe_ltp.get("ltp")
        straddle = (
            float(ce_p) + float(pe_p)
            if ce_p is not None and pe_p is not None
            else None
        )

        pcr_regime = _pcr_regime(total_pcr)
        dist_call = (
            (call_wall_oi - state.spot) / state.spot * 100.0
            if call_wall_oi and state.spot
            else None
        )
        dist_put = (
            (state.spot - put_wall_oi) / state.spot * 100.0
            if put_wall_oi and state.spot
            else None
        )

        return {
            "total_oi_pcr": round(total_pcr, 4) if total_pcr is not None else None,
            "atm_pcr": round(atm_pcr, 4) if atm_pcr is not None else None,
            "atm_pcr_wing": ATM_PCR_WING,
            "atm_pcr_strikes": band,
            "volume_pcr": round(vol_pcr, 4) if vol_pcr is not None else None,
            "max_pain": pain,
            "call_wall": call_wall_oi,
            "put_wall": put_wall_oi,
            "call_wall_oi_addition": call_wall_add,
            "put_wall_oi_addition": put_wall_add,
            "atm_straddle_premium": round(straddle, 4) if straddle is not None else None,
            "total_call_oi": tot_ce,
            "total_put_oi": tot_pe,
            "total_call_volume": call_vol,
            "total_put_volume": put_vol,
            "pcr_regime": pcr_regime,
            "spot_to_call_wall_pct": round(dist_call, 4) if dist_call is not None else None,
            "spot_to_put_wall_pct": round(dist_put, 4) if dist_put is not None else None,
        }


def _pcr_regime(pcr: Optional[float]) -> str:
    if pcr is None:
        return "UNKNOWN"
    if pcr >= 1.2:
        return "PUT_HEAVY"  # historically supportive / bullish tilt
    if pcr <= 0.7:
        return "CALL_HEAVY"  # historically resistive / bearish tilt
    return "BALANCED"


def apply_chain_to_signal(signal: dict[str, Any], chain: dict[str, Any] | None) -> dict[str, Any]:
    """
    Wire PCR regime + Call/Put wall proximity into a desk signal (mutates copy).
    """
    if not chain or not isinstance(chain, dict):
        out = dict(signal)
        out["option_chain"] = {"available": False, "reason": "chain_inactive"}
        return out
    analytics = chain.get("analytics") or {}
    out = dict(signal)
    tags = list(out.get("tags") or [])
    score = float(out.get("score") or 50.0)
    conf = float(out.get("confidence") or 50.0)
    side = str(out.get("side") or "HOLD").upper()
    spot = float(chain.get("spot") or out.get("price") or 0)
    thesis_bits: list[str] = []

    regime = analytics.get("pcr_regime") or "UNKNOWN"
    tags.append(f"PCR_{regime}")
    if regime == "PUT_HEAVY" and side == "BUY":
        score += 4
        conf += 3
        thesis_bits.append(f"OI-PCR {analytics.get('total_oi_pcr')} put-heavy")
    elif regime == "PUT_HEAVY" and side == "SELL":
        score -= 3
        conf -= 2
        thesis_bits.append("put-heavy PCR vs SELL bias")
    elif regime == "CALL_HEAVY" and side == "SELL":
        score += 4
        conf += 3
        thesis_bits.append(f"OI-PCR {analytics.get('total_oi_pcr')} call-heavy")
    elif regime == "CALL_HEAVY" and side == "BUY":
        score -= 3
        conf -= 2
        thesis_bits.append("call-heavy PCR vs BUY bias")

    call_wall = analytics.get("call_wall")
    put_wall = analytics.get("put_wall")
    # Proximity: within ~0.4% of wall
    if call_wall and spot > 0:
        dist = (call_wall - spot) / spot
        if 0 <= dist <= 0.004 and side == "BUY":
            tags.append("NEAR_CALL_WALL")
            score -= 5
            conf -= 4
            thesis_bits.append(f"near Call Wall {call_wall:.0f}")
        elif dist < 0 and side == "BUY":
            tags.append("ABOVE_CALL_WALL")
    if put_wall and spot > 0:
        dist = (spot - put_wall) / spot
        if 0 <= dist <= 0.004 and side == "SELL":
            tags.append("NEAR_PUT_WALL")
            score -= 5
            conf -= 4
            thesis_bits.append(f"near Put Wall {put_wall:.0f}")
        elif dist < 0 and side == "SELL":
            tags.append("BELOW_PUT_WALL")

    mp = analytics.get("max_pain")
    if mp and spot > 0:
        tags.append("MAX_PAIN")
        thesis_bits.append(f"MaxPain {mp:.0f}")

    fut_b = ((chain.get("future") or {}).get("buildup") or {}).get("label")
    if fut_b and fut_b != "Unknown":
        tags.append(f"FUT_{fut_b.replace(' ', '_').upper()}")

    score = max(0.0, min(100.0, score))
    conf = max(15.0, min(92.0, conf))
    # Wall proximity can force HOLD caution without inventing a flip
    if "NEAR_CALL_WALL" in tags and side == "BUY" and score < 55:
        side = "HOLD"
        conf = min(conf, 48.0)
        thesis_bits.append("BUY→HOLD (call wall)")
    if "NEAR_PUT_WALL" in tags and side == "SELL" and score > 45:
        side = "HOLD"
        conf = min(conf, 48.0)
        thesis_bits.append("SELL→HOLD (put wall)")

    thesis = str(out.get("thesis") or "")
    if thesis_bits:
        thesis = f"{thesis} · chain: {'; '.join(thesis_bits)}"

    out.update(
        {
            "side": side,
            "score": round(score, 1),
            "confidence": round(conf, 1),
            "tags": list(dict.fromkeys(tags)),
            "thesis": thesis,
            "option_chain": {
                "available": True,
                "expiry": chain.get("expiry"),
                "spot": chain.get("spot"),
                "atm": chain.get("atm"),
                "analytics": {
                    k: analytics.get(k)
                    for k in (
                        "total_oi_pcr",
                        "atm_pcr",
                        "volume_pcr",
                        "max_pain",
                        "call_wall",
                        "put_wall",
                        "atm_straddle_premium",
                        "pcr_regime",
                        "spot_to_call_wall_pct",
                        "spot_to_put_wall_pct",
                    )
                },
                "future_buildup": (chain.get("future") or {}).get("buildup"),
            },
        }
    )
    return out


_engine: Optional[OptionChainEngine] = None
_engine_lock = threading.Lock()


def get_option_chain_engine() -> OptionChainEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = OptionChainEngine()
        return _engine
