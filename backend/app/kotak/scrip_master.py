"""
Kotak daily Scrip Master downloader / cache / F&O token resolver.

Downloads public CSVs from lapi (nse_cm, bse_cm, nse_fo, bse_fo), caches locally,
and resolves equities / futures / options to exact Kotak instrument_token IDs.
Never hardcodes tokens.
"""
from __future__ import annotations

import io
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "kotak_cache"
_SEGMENTS = ("nse_cm", "bse_cm", "nse_fo", "bse_fo")
_LAPI = "https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod"
# Kotak FO expiry timestamps are offset from Unix epoch by this constant.
_EXPIRY_EPOCH_OFFSET = 315_513_000
_OPTION_RIGHTS = frozenset({"CE", "PE", "CA", "PA"})

OptionRight = Literal["CE", "PE"]
InstKind = Literal["EQ", "FUT", "OPT", "INDEX", "OTHER"]


@dataclass(frozen=True)
class Instrument:
    """Resolved Kotak instrument — token is always from scrip master, never hardcoded."""

    exchange_segment: str
    instrument_token: str
    symbol: str
    trading_symbol: str
    kind: InstKind
    underlying: str
    expiry: Optional[date]
    strike: Optional[float]
    option_right: Optional[OptionRight]
    lot_size: int
    tick_size: float
    instrument_type: str

    def key(self) -> str:
        return f"{self.exchange_segment}|{self.instrument_token}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expiry"] = self.expiry.isoformat() if self.expiry else None
        return d


def _col(df: pd.DataFrame, *names: str) -> Optional[str]:
    lower = {c.strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _decode_expiry(raw: Any) -> Optional[date]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        ts = int(float(raw))
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    # Cash / some rows already look like unix seconds in recent years.
    if ts > 1_600_000_000:  # ~2020+
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return datetime.fromtimestamp(ts + _EXPIRY_EPOCH_OFFSET, tz=timezone.utc).date()


def _strike(raw: Any) -> Optional[float]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    # FO CSV stores strikes × 100 (e.g. 1855000 → 18550).
    if abs(v) >= 1000 and abs(v) == int(abs(v)):
        return v / 100.0
    return v


def _tick(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.05
    if v <= 0:
        return 0.05
    # Tick often stored × 100 (10 → 0.10).
    if v >= 1 and v == int(v):
        return v / 100.0
    return v


def _lot(raw: Any) -> int:
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return 1


def _classify(inst_type: str, group: str, segment: str) -> InstKind:
    it = (inst_type or "").upper()
    g = (group or "").upper()
    if it in ("OPTIDX", "OPTSTK", "OPTCUR", "OPTCOM") or it.startswith("OPT"):
        return "OPT"
    if it in ("FUTIDX", "FUTSTK", "FUTCUR", "FUTCOM") or it.startswith("FUT"):
        return "FUT"
    if "fo" in segment and it in ("", "XX"):
        return "OTHER"
    if g == "EQ" or it in ("EQ", "BE"):
        return "EQ"
    if it in ("INDEX", "IDX") or g == "IF":
        return "INDEX"
    if segment.endswith("_cm") and g == "EQ":
        return "EQ"
    return "OTHER"


def _right(raw: Any) -> Optional[OptionRight]:
    s = str(raw or "").strip().upper()
    if s in ("CE", "CA", "C", "CALL"):
        return "CE"
    if s in ("PE", "PA", "P", "PUT"):
        return "PE"
    return None


class ScripMaster:
    """Thread-safe daily cache of Kotak scrip CSVs + resolvers."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else _CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._frames: dict[str, pd.DataFrame] = {}
        self._as_of: Optional[str] = None
        self._instruments: list[Instrument] = []
        self._by_token: dict[str, Instrument] = {}
        self._eq_by_symbol: dict[str, Instrument] = {}

    def ensure_loaded(self, *, force: bool = False) -> str:
        with self._lock:
            if self._instruments and not force:
                return self._as_of or ""
            as_of, frames = self._download_all()
            instruments = self._parse_all(frames)
            self._frames = frames
            self._as_of = as_of
            self._instruments = instruments
            self._by_token = {i.key(): i for i in instruments}
            self._eq_by_symbol = {}
            for inst in instruments:
                if inst.kind == "EQ" and inst.exchange_segment == "nse_cm":
                    self._eq_by_symbol[inst.symbol.upper()] = inst
            logger.info(
                "scrip_master_loaded as_of=%s instruments=%d eq=%d",
                as_of,
                len(instruments),
                len(self._eq_by_symbol),
            )
            return as_of

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "as_of": self._as_of,
                "segments": {s: int(len(self._frames.get(s, []))) for s in _SEGMENTS},
                "instruments": len(self._instruments),
                "nse_eq": len(self._eq_by_symbol),
                "cache_dir": str(self.cache_dir),
            }

    def get_by_token(self, exchange_segment: str, instrument_token: str) -> Optional[Instrument]:
        self.ensure_loaded()
        key = f"{exchange_segment}|{str(instrument_token)}"
        with self._lock:
            return self._by_token.get(key)

    def resolve_equity(
        self,
        symbol: str,
        *,
        exchange_segment: str = "nse_cm",
    ) -> Instrument:
        self.ensure_loaded()
        sym = symbol.upper().strip().replace(".NS", "").replace("-EQ", "")
        with self._lock:
            if exchange_segment == "nse_cm" and sym in self._eq_by_symbol:
                return self._eq_by_symbol[sym]
            matches = [
                i
                for i in self._instruments
                if i.exchange_segment == exchange_segment
                and i.kind == "EQ"
                and (i.symbol == sym or i.trading_symbol.upper() in (sym, f"{sym}-EQ"))
            ]
        if not matches:
            raise LookupError(
                f"No equity instrument for {sym!r} on {exchange_segment} "
                f"(scrip master as_of={self._as_of})"
            )
        return matches[0]

    def resolve_future(
        self,
        underlying: str,
        expiry: date | str,
        *,
        exchange_segment: str = "nse_fo",
    ) -> Instrument:
        self.ensure_loaded()
        und = underlying.upper().strip()
        exp = _as_date(expiry)
        with self._lock:
            matches = [
                i
                for i in self._instruments
                if i.exchange_segment == exchange_segment
                and i.kind == "FUT"
                and i.underlying == und
                and i.expiry == exp
            ]
        if not matches:
            raise LookupError(
                f"No future for {und} expiry={exp.isoformat()} on {exchange_segment}"
            )
        return matches[0]

    def resolve_option(
        self,
        underlying: str,
        expiry: date | str,
        strike: float,
        right: str,
        *,
        exchange_segment: str = "nse_fo",
    ) -> Instrument:
        self.ensure_loaded()
        und = underlying.upper().strip()
        exp = _as_date(expiry)
        opt = _right(right)
        if opt is None:
            raise ValueError(f"option right must be CE/PE, got {right!r}")
        strike_f = float(strike)
        with self._lock:
            matches = [
                i
                for i in self._instruments
                if i.exchange_segment == exchange_segment
                and i.kind == "OPT"
                and i.underlying == und
                and i.expiry == exp
                and i.option_right == opt
                and i.strike is not None
                and abs(i.strike - strike_f) < 1e-6
            ]
        if not matches:
            raise LookupError(
                f"No option {und} {exp.isoformat()} {strike_f} {opt} on {exchange_segment}"
            )
        return matches[0]

    def nearest_future(
        self,
        underlying: str,
        *,
        exchange_segment: str = "nse_fo",
        as_of: date | None = None,
    ) -> Instrument:
        """Nearest non-expired future for an underlying (index or stock)."""
        self.ensure_loaded()
        und = underlying.upper().strip()
        today = as_of or datetime.now(timezone.utc).date()
        with self._lock:
            cands = [
                i
                for i in self._instruments
                if i.exchange_segment == exchange_segment
                and i.kind == "FUT"
                and i.underlying == und
                and i.expiry is not None
                and i.expiry >= today
            ]
        if not cands:
            raise LookupError(f"No live futures for {und} on {exchange_segment}")
        cands.sort(key=lambda i: i.expiry or date.max)
        return cands[0]

    def list_expiries(
        self,
        underlying: str,
        *,
        kind: InstKind = "OPT",
        exchange_segment: str = "nse_fo",
    ) -> list[str]:
        self.ensure_loaded()
        und = underlying.upper().strip()
        with self._lock:
            exps = sorted(
                {
                    i.expiry.isoformat()
                    for i in self._instruments
                    if i.exchange_segment == exchange_segment
                    and i.kind == kind
                    and i.underlying == und
                    and i.expiry is not None
                }
            )
        return exps

    def option_chain_tokens(
        self,
        underlying: str,
        expiry: date | str,
        *,
        exchange_segment: str = "nse_fo",
    ) -> list[Instrument]:
        self.ensure_loaded()
        und = underlying.upper().strip()
        exp = _as_date(expiry)
        with self._lock:
            return [
                i
                for i in self._instruments
                if i.exchange_segment == exchange_segment
                and i.kind == "OPT"
                and i.underlying == und
                and i.expiry == exp
            ]

    def nse_eq_token_map(self) -> dict[str, str]:
        self.ensure_loaded()
        with self._lock:
            return {s: i.instrument_token for s, i in self._eq_by_symbol.items()}

    # --- download / parse -------------------------------------------------

    def _download_all(self) -> tuple[str, dict[str, pd.DataFrame]]:
        today = datetime.now().date()
        frames: dict[str, pd.DataFrame] = {}
        as_of: Optional[str] = None
        for offset in range(0, 7):
            day = (today - timedelta(days=offset)).isoformat()
            day_frames: dict[str, pd.DataFrame] = {}
            ok = True
            for seg in _SEGMENTS:
                df = self._load_segment(seg, day)
                if df is None or df.empty:
                    ok = False
                    break
                day_frames[seg] = df
            if ok:
                frames = day_frames
                as_of = day
                break
        if not frames or not as_of:
            raise RuntimeError(
                "Failed to download Kotak scrip master CSVs for any of the last 7 days "
                f"from {_LAPI}"
            )
        return as_of, frames

    def _load_segment(self, segment: str, day: str) -> Optional[pd.DataFrame]:
        cache = self.cache_dir / f"{segment}_{day}.csv"
        if cache.exists() and cache.stat().st_size > 1000:
            try:
                return pd.read_csv(cache, low_memory=False)
            except Exception as e:
                logger.warning("corrupt cache %s: %s", cache, e)
        url = f"{_LAPI}/{day}/transformed/{segment}.csv"
        try:
            r = requests.get(url, timeout=90)
            if r.status_code != 200 or len(r.content) < 1000:
                logger.warning("scrip CSV %s → HTTP %s len=%s", url, r.status_code, len(r.content))
                return None
            cache.write_bytes(r.content)
            return pd.read_csv(io.BytesIO(r.content), low_memory=False)
        except Exception as e:
            logger.warning("scrip CSV download failed %s: %s", url, e)
            return None

    def _parse_all(self, frames: dict[str, pd.DataFrame]) -> list[Instrument]:
        out: list[Instrument] = []
        for segment, df in frames.items():
            out.extend(self._parse_frame(segment, df))
        return out

    def _parse_frame(self, segment: str, df: pd.DataFrame) -> list[Instrument]:
        if df.empty:
            return []
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        tok_c = _col(df, "pSymbol", "p_symbol")
        name_c = _col(df, "pSymbolName", "p_symbol_name")
        trd_c = _col(df, "pTrdSymbol", "p_trd_symbol")
        group_c = _col(df, "pGroup", "p_group")
        inst_c = _col(df, "pInstType", "p_inst_type")
        lot_c = _col(df, "lLotSize", "l_lot_size")
        tick_c = _col(df, "dTickSize", "d_tick_size", "dTickSize ")
        strike_c = _col(df, "dStrikePrice;", "dStrikePrice", "d_strike_price")
        right_c = _col(df, "pOptionType", "p_option_type")
        exp_c = _col(df, "pExpiryDate", "lExpiryDate", "lExpiryDate ", "pMaturityDate")
        und_c = _col(df, "pSymbolName", "p_symbol_name")  # underlying name for FO
        if not tok_c:
            logger.error("scrip segment %s missing pSymbol column", segment)
            return []

        instruments: list[Instrument] = []
        for _, row in df.iterrows():
            try:
                token = str(int(float(row[tok_c])))
            except (TypeError, ValueError):
                continue
            symbol = str(row[name_c]).strip().upper() if name_c else ""
            trading = str(row[trd_c]).strip() if trd_c else symbol
            group = str(row[group_c]).strip() if group_c else ""
            if group.lower() == "nan":
                group = ""
            raw_inst = row[inst_c] if inst_c else ""
            if raw_inst is None or (isinstance(raw_inst, float) and pd.isna(raw_inst)):
                inst_type = ""
            else:
                inst_type = str(raw_inst).strip().upper()
                if inst_type == "NAN":
                    inst_type = ""
            kind = _classify(inst_type, group, segment)
            if segment.endswith("_cm") and kind == "OTHER" and group.upper() != "EQ":
                # Skip bonds / ETFs / noise for cash unless explicitly EQ.
                if group.upper() not in ("EQ", "BE", "SM", "IF"):
                    continue
            right = _right(row[right_c]) if right_c and kind == "OPT" else None
            if kind == "OPT" and right is None:
                # Some rows encode right in trading symbol suffix.
                ts = trading.upper()
                if ts.endswith("CE"):
                    right = "CE"
                elif ts.endswith("PE"):
                    right = "PE"
            underlying = symbol
            if und_c and kind in ("FUT", "OPT"):
                underlying = str(row[und_c]).strip().upper() or symbol
            instruments.append(
                Instrument(
                    exchange_segment=segment,
                    instrument_token=token,
                    symbol=symbol or trading,
                    trading_symbol=trading or symbol,
                    kind=kind if kind != "OTHER" or group.upper() == "EQ" else "OTHER",
                    underlying=underlying,
                    expiry=_decode_expiry(row[exp_c]) if exp_c else None,
                    strike=_strike(row[strike_c]) if strike_c and kind == "OPT" else None,
                    option_right=right,
                    lot_size=_lot(row[lot_c]) if lot_c else 1,
                    tick_size=_tick(row[tick_c]) if tick_c else 0.05,
                    instrument_type=inst_type or group.upper() or kind,
                )
            )
        return instruments


def _as_date(value: date | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    return date.fromisoformat(s)


_master: Optional[ScripMaster] = None
_master_lock = threading.Lock()


def get_scrip_master() -> ScripMaster:
    global _master
    with _master_lock:
        if _master is None:
            _master = ScripMaster()
        return _master
