"""
Manual trade journal + capital accounting.

All positions and cash movements are **user-entered research records**,
not verified broker executions. Corrections soft-supersede prior rows and
append an audit event (history is retained).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from app.config import config

_lock = threading.Lock()

Direction = Literal["LONG", "SHORT"]
TradeStatus = Literal["open", "closed"]
MovementKind = Literal["starting_capital", "deposit", "withdrawal"]

SOURCE_LABEL = "user_entered_not_broker_fill"
DISCLAIMER = (
    "User-entered research journal only — not verified broker fills, "
    "not custody, and not investment advice."
)


def _db_path(path: Path | None = None) -> Path:
    p = path or (config.data_dir / "trade_ledger.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(_db_path(path)), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


SCHEMA = """
CREATE TABLE IF NOT EXISTS capital_movements (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  amount REAL NOT NULL,
  occurred_at TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT
);
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY,
  instrument TEXT NOT NULL,
  direction TEXT NOT NULL,
  status TEXT NOT NULL,
  quantity REAL NOT NULL,
  entry_qty REAL NOT NULL,
  entry_price REAL NOT NULL,
  entry_at TEXT NOT NULL,
  exit_avg_price REAL,
  exit_at TEXT,
  lots REAL,
  fees_total REAL NOT NULL DEFAULT 0,
  notes TEXT,
  source_label TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS trade_exits (
  id TEXT PRIMARY KEY,
  trade_id TEXT NOT NULL,
  quantity REAL NOT NULL,
  price REAL NOT NULL,
  exited_at TEXT NOT NULL,
  fees REAL NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(trade_id) REFERENCES trades(id)
);
CREATE TABLE IF NOT EXISTS ledger_audit (
  id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_active ON trades(active, status);
CREATE INDEX IF NOT EXISTS idx_exits_trade ON trade_exits(trade_id, active);
CREATE INDEX IF NOT EXISTS idx_moves_active ON capital_movements(active, kind);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON ledger_audit(entity_type, entity_id);
"""


def ensure_schema(path: Path | None = None) -> Path:
    p = _db_path(path)
    with _lock:
        con = _conn(p)
        try:
            con.executescript(SCHEMA)
            con.commit()
        finally:
            con.close()
    return p


def _audit(
    con: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO ledger_audit(
          id, entity_type, entity_id, action, before_json, after_json, reason, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            entity_type,
            entity_id,
            action,
            None if before is None else json.dumps(before, ensure_ascii=False),
            None if after is None else json.dumps(after, ensure_ascii=False),
            (reason or "").strip() or None,
            _now(),
        ),
    )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


# ---- capital movements ----------------------------------------------------


def add_capital_movement(
    *,
    kind: MovementKind,
    amount: float,
    occurred_at: str | None = None,
    notes: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    ensure_schema(path)
    kind = str(kind).strip().lower()  # type: ignore[assignment]
    if kind not in ("starting_capital", "deposit", "withdrawal"):
        raise ValueError("kind must be starting_capital | deposit | withdrawal")
    amt = float(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")
    if kind == "starting_capital" and amt == 0:
        raise ValueError("starting_capital must be > 0")

    rec = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "amount": round(amt, 2),
        "occurred_at": occurred_at or _now(),
        "notes": (notes or "").strip() or None,
        "created_at": _now(),
        "active": 1,
        "supersedes_id": None,
        "source_label": SOURCE_LABEL,
        "disclaimer": DISCLAIMER,
    }
    with _lock:
        con = _conn(path)
        try:
            if kind == "starting_capital":
                # Only one active starting capital
                existing = con.execute(
                    "SELECT id FROM capital_movements WHERE kind=? AND active=1",
                    ("starting_capital",),
                ).fetchone()
                if existing:
                    raise ValueError(
                        "starting_capital already set — use correct_capital_movement "
                        "with a reason to change it"
                    )
            con.execute(
                """
                INSERT INTO capital_movements(
                  id, kind, amount, occurred_at, notes, created_at, active, supersedes_id
                ) VALUES (?,?,?,?,?,?,1,NULL)
                """,
                (
                    rec["id"],
                    rec["kind"],
                    rec["amount"],
                    rec["occurred_at"],
                    rec["notes"],
                    rec["created_at"],
                ),
            )
            _audit(
                con,
                entity_type="capital_movement",
                entity_id=rec["id"],
                action="create",
                after=rec,
            )
            con.commit()
        finally:
            con.close()
    return rec


def correct_capital_movement(
    movement_id: str,
    *,
    amount: float,
    reason: str,
    notes: str | None = None,
    occurred_at: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Soft-supersede a movement; prior row stays inactive for history."""
    ensure_schema(path)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required for corrections")
    amt = float(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")

    with _lock:
        con = _conn(path)
        try:
            old = con.execute(
                "SELECT * FROM capital_movements WHERE id=? AND active=1",
                (movement_id,),
            ).fetchone()
            if not old:
                raise LookupError(f"active capital movement not found: {movement_id}")
            before = _row_to_dict(old)
            new_id = str(uuid.uuid4())
            after = {
                "id": new_id,
                "kind": old["kind"],
                "amount": round(amt, 2),
                "occurred_at": occurred_at or old["occurred_at"],
                "notes": (notes if notes is not None else old["notes"]),
                "created_at": _now(),
                "active": 1,
                "supersedes_id": movement_id,
                "source_label": SOURCE_LABEL,
                "disclaimer": DISCLAIMER,
            }
            con.execute(
                "UPDATE capital_movements SET active=0 WHERE id=?", (movement_id,)
            )
            con.execute(
                """
                INSERT INTO capital_movements(
                  id, kind, amount, occurred_at, notes, created_at, active, supersedes_id
                ) VALUES (?,?,?,?,?,?,1,?)
                """,
                (
                    after["id"],
                    after["kind"],
                    after["amount"],
                    after["occurred_at"],
                    after["notes"],
                    after["created_at"],
                    movement_id,
                ),
            )
            _audit(
                con,
                entity_type="capital_movement",
                entity_id=new_id,
                action="correct",
                before=before,
                after=after,
                reason=reason,
            )
            con.commit()
            return after
        finally:
            con.close()


def list_capital_movements(
    *, include_inactive: bool = False, path: Path | None = None
) -> list[dict[str, Any]]:
    ensure_schema(path)
    with _lock:
        con = _conn(path)
        try:
            q = "SELECT * FROM capital_movements"
            if not include_inactive:
                q += " WHERE active=1"
            q += " ORDER BY occurred_at ASC, created_at ASC"
            rows = con.execute(q).fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]
        finally:
            con.close()


# ---- trades ---------------------------------------------------------------


def _gross_pnl_for_exit(
    *, direction: str, entry_price: float, exit_price: float, qty: float
) -> float:
    if direction == "LONG":
        return (float(exit_price) - float(entry_price)) * float(qty)
    return (float(entry_price) - float(exit_price)) * float(qty)


def _realized_for_exit(
    *, direction: str, entry_price: float, exit_price: float, qty: float, fees: float
) -> float:
    """Per-leg net of that leg's fees only (entry fees accounted in summary)."""
    gross = _gross_pnl_for_exit(
        direction=direction, entry_price=entry_price, exit_price=exit_price, qty=qty
    )
    return round(gross - float(fees or 0), 2)


def open_trade(
    *,
    instrument: str,
    direction: Direction,
    quantity: float,
    entry_price: float,
    entry_at: str | None = None,
    lots: float | None = None,
    fees: float = 0.0,
    notes: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    ensure_schema(path)
    instrument = str(instrument or "").strip().upper()
    direction = str(direction or "").strip().upper()  # type: ignore[assignment]
    if not instrument:
        raise ValueError("instrument required")
    if direction not in ("LONG", "SHORT"):
        raise ValueError("direction must be LONG or SHORT")
    qty = float(quantity)
    px = float(entry_price)
    fee = float(fees or 0)
    if qty <= 0 or px <= 0:
        raise ValueError("quantity and entry_price must be > 0")
    if fee < 0:
        raise ValueError("fees must be >= 0")

    now = _now()
    rec = {
        "id": str(uuid.uuid4()),
        "instrument": instrument,
        "direction": direction,
        "status": "open",
        "quantity": qty,
        "entry_qty": qty,
        "entry_price": round(px, 6),
        "entry_at": entry_at or now,
        "exit_avg_price": None,
        "exit_at": None,
        "lots": None if lots is None else float(lots),
        "fees_total": round(fee, 2),
        "notes": (notes or "").strip() or None,
        "source_label": SOURCE_LABEL,
        "created_at": now,
        "updated_at": now,
        "active": 1,
        "disclaimer": DISCLAIMER,
    }
    with _lock:
        con = _conn(path)
        try:
            con.execute(
                """
                INSERT INTO trades(
                  id, instrument, direction, status, quantity, entry_qty, entry_price,
                  entry_at, exit_avg_price, exit_at, lots, fees_total, notes,
                  source_label, created_at, updated_at, active
                ) VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,?,1)
                """,
                (
                    rec["id"],
                    rec["instrument"],
                    rec["direction"],
                    rec["status"],
                    rec["quantity"],
                    rec["entry_qty"],
                    rec["entry_price"],
                    rec["entry_at"],
                    rec["lots"],
                    rec["fees_total"],
                    rec["notes"],
                    rec["source_label"],
                    rec["created_at"],
                    rec["updated_at"],
                ),
            )
            _audit(
                con,
                entity_type="trade",
                entity_id=rec["id"],
                action="create",
                after=rec,
            )
            con.commit()
        finally:
            con.close()
    return rec


def record_exit(
    trade_id: str,
    *,
    quantity: float,
    price: float,
    exited_at: str | None = None,
    fees: float = 0.0,
    notes: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Partial or full exit against an open user-entered trade."""
    ensure_schema(path)
    qty = float(quantity)
    px = float(price)
    fee = float(fees or 0)
    if qty <= 0 or px <= 0:
        raise ValueError("quantity and price must be > 0")
    if fee < 0:
        raise ValueError("fees must be >= 0")

    with _lock:
        con = _conn(path)
        try:
            trade = con.execute(
                "SELECT * FROM trades WHERE id=? AND active=1", (trade_id,)
            ).fetchone()
            if not trade:
                raise LookupError(f"active trade not found: {trade_id}")
            if trade["status"] != "open":
                raise ValueError("trade is already closed")
            remaining = float(trade["quantity"])
            if qty - remaining > 1e-9:
                raise ValueError(
                    f"exit quantity {qty} exceeds remaining open quantity {remaining}"
                )
            before = _row_to_dict(trade)
            exit_id = str(uuid.uuid4())
            now = _now()
            exit_at = exited_at or now
            exit_rec = {
                "id": exit_id,
                "trade_id": trade_id,
                "quantity": round(qty, 6),
                "price": round(px, 6),
                "exited_at": exit_at,
                "fees": round(fee, 2),
                "notes": (notes or "").strip() or None,
                "created_at": now,
                "active": 1,
                "realized_pnl": _realized_for_exit(
                    direction=trade["direction"],
                    entry_price=float(trade["entry_price"]),
                    exit_price=px,
                    qty=qty,
                    fees=fee,
                ),
                "source_label": SOURCE_LABEL,
            }
            con.execute(
                """
                INSERT INTO trade_exits(
                  id, trade_id, quantity, price, exited_at, fees, notes, created_at, active
                ) VALUES (?,?,?,?,?,?,?,?,1)
                """,
                (
                    exit_id,
                    trade_id,
                    exit_rec["quantity"],
                    exit_rec["price"],
                    exit_rec["exited_at"],
                    exit_rec["fees"],
                    exit_rec["notes"],
                    now,
                ),
            )
            new_qty = round(remaining - qty, 6)
            # Weighted average exit price across all active exits
            exits = con.execute(
                "SELECT quantity, price FROM trade_exits WHERE trade_id=? AND active=1",
                (trade_id,),
            ).fetchall()
            tot_q = sum(float(e["quantity"]) for e in exits)
            avg_exit = (
                sum(float(e["quantity"]) * float(e["price"]) for e in exits) / tot_q
                if tot_q > 0
                else None
            )
            fees_total = round(float(trade["fees_total"]) + fee, 2)
            status = "closed" if new_qty <= 1e-9 else "open"
            if status == "closed":
                new_qty = 0.0
            con.execute(
                """
                UPDATE trades SET quantity=?, status=?, exit_avg_price=?, exit_at=?,
                  fees_total=?, updated_at=? WHERE id=?
                """,
                (
                    new_qty,
                    status,
                    None if avg_exit is None else round(avg_exit, 6),
                    exit_at if status == "closed" else trade["exit_at"],
                    fees_total,
                    now,
                    trade_id,
                ),
            )
            after = _row_to_dict(
                con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            )
            _audit(
                con,
                entity_type="trade_exit",
                entity_id=exit_id,
                action="create",
                before=before,
                after={"trade": after, "exit": exit_rec},
            )
            con.commit()
            return {"trade": after, "exit": exit_rec, "disclaimer": DISCLAIMER}
        finally:
            con.close()


def correct_trade(
    trade_id: str,
    *,
    reason: str,
    notes: str | None = None,
    entry_price: float | None = None,
    lots: float | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Correct mutable metadata on an active trade; audited."""
    ensure_schema(path)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required for corrections")
    with _lock:
        con = _conn(path)
        try:
            trade = con.execute(
                "SELECT * FROM trades WHERE id=? AND active=1", (trade_id,)
            ).fetchone()
            if not trade:
                raise LookupError(f"active trade not found: {trade_id}")
            before = _row_to_dict(trade)
            new_notes = notes if notes is not None else trade["notes"]
            new_px = (
                round(float(entry_price), 6)
                if entry_price is not None
                else trade["entry_price"]
            )
            if entry_price is not None and float(entry_price) <= 0:
                raise ValueError("entry_price must be > 0")
            new_lots = float(lots) if lots is not None else trade["lots"]
            now = _now()
            con.execute(
                """
                UPDATE trades SET notes=?, entry_price=?, lots=?, updated_at=?
                WHERE id=?
                """,
                (new_notes, new_px, new_lots, now, trade_id),
            )
            after = _row_to_dict(
                con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            )
            _audit(
                con,
                entity_type="trade",
                entity_id=trade_id,
                action="correct",
                before=before,
                after=after,
                reason=reason,
            )
            con.commit()
            return {**(after or {}), "disclaimer": DISCLAIMER}
        finally:
            con.close()


def soft_delete_trade(
    trade_id: str, *, reason: str, path: Path | None = None
) -> dict[str, Any]:
    ensure_schema(path)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required")
    with _lock:
        con = _conn(path)
        try:
            trade = con.execute(
                "SELECT * FROM trades WHERE id=? AND active=1", (trade_id,)
            ).fetchone()
            if not trade:
                raise LookupError(f"active trade not found: {trade_id}")
            before = _row_to_dict(trade)
            con.execute(
                "UPDATE trades SET active=0, updated_at=? WHERE id=?", (_now(), trade_id)
            )
            con.execute(
                "UPDATE trade_exits SET active=0 WHERE trade_id=?", (trade_id,)
            )
            _audit(
                con,
                entity_type="trade",
                entity_id=trade_id,
                action="soft_delete",
                before=before,
                after={"active": 0},
                reason=reason,
            )
            con.commit()
            return {"id": trade_id, "active": 0, "disclaimer": DISCLAIMER}
        finally:
            con.close()


def list_trades(
    *,
    status: str | None = None,
    include_inactive: bool = False,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    ensure_schema(path)
    with _lock:
        con = _conn(path)
        try:
            clauses = []
            args: list[Any] = []
            if not include_inactive:
                clauses.append("active=1")
            if status:
                clauses.append("status=?")
                args.append(status)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = con.execute(
                f"SELECT * FROM trades{where} ORDER BY entry_at DESC", args
            ).fetchall()
            out = []
            for r in rows:
                d = _row_to_dict(r)
                assert d
                exits = con.execute(
                    "SELECT * FROM trade_exits WHERE trade_id=? AND active=1 ORDER BY exited_at",
                    (d["id"],),
                ).fetchall()
                exit_dicts = []
                realized_gross = 0.0
                exit_fees = 0.0
                for e in exits:
                    ed = _row_to_dict(e)
                    assert ed
                    gross = _gross_pnl_for_exit(
                        direction=d["direction"],
                        entry_price=float(d["entry_price"]),
                        exit_price=float(ed["price"]),
                        qty=float(ed["quantity"]),
                    )
                    fee = float(ed["fees"] or 0)
                    ed["realized_gross"] = round(gross, 2)
                    ed["realized_pnl"] = round(gross - fee, 2)
                    realized_gross += gross
                    exit_fees += fee
                    exit_dicts.append(ed)
                fees_total = float(d.get("fees_total") or 0)
                # Net realized = exit gross − all trade fees (entry + exits)
                d["exits"] = exit_dicts
                d["realized_gross"] = round(realized_gross, 2)
                d["realized_pnl"] = round(realized_gross - fees_total, 2)
                d["exit_fees"] = round(exit_fees, 2)
                d["source_label"] = d.get("source_label") or SOURCE_LABEL
                d["disclaimer"] = DISCLAIMER
                out.append(d)
            return out
        finally:
            con.close()


def list_audit(
    *, limit: int = 100, path: Path | None = None
) -> list[dict[str, Any]]:
    ensure_schema(path)
    with _lock:
        con = _conn(path)
        try:
            rows = con.execute(
                "SELECT * FROM ledger_audit ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]
        finally:
            con.close()


# ---- quotes / unrealized / summary ----------------------------------------


def _reliable_quote(instrument: str) -> dict[str, Any]:
    """
    Return quote only when considered usable for estimated unrealized P&L.

    LIVE + age <= LIVE_QUOTE_STALE_SEC → reliable.
    FALLBACK → estimated with research_fallback label (still shown separately).
    Else unavailable.
    """
    try:
        from app import live_quotes
        from app.market_types import is_broker_live_claim

        # NSE cash convention used elsewhere
        yahoo = (
            instrument
            if instrument.startswith("^") or instrument.endswith(".NS")
            else f"{instrument}.NS"
        )
        if instrument in ("NIFTY", "NIFTY50"):
            yahoo = "^NSEI"
        elif instrument in ("BANKNIFTY",):
            yahoo = "^NSEBANK"
        q = live_quotes.quote_snapshot(yahoo)
        age = float(q.age_sec) if q.age_sec is not None else None
        stale_lim = float(config.live_quote_stale_sec or 5.0)
        state = getattr(q, "market_data_state", None) or q.feed_status
        ltp = float(q.ltp) if q.ltp is not None else None
        if ltp is None or ltp <= 0:
            return {
                "available": False,
                "reason": "no_ltp",
                "reliability": "unavailable",
            }
        broker_live = bool(
            getattr(q, "is_current_live", False)
        ) or is_broker_live_claim(str(state), q.source)
        if broker_live and age is not None and age <= stale_lim:
            return {
                "available": True,
                "ltp": ltp,
                "source": q.source,
                "age_sec": age,
                "reliability": "live_quote",
                "label": "estimated_unrealized_live_quote",
            }
        if str(q.feed_status).upper() in ("LIVE", "FALLBACK") or str(state).upper() in (
            "LIVE",
            "FALLBACK",
        ):
            if age is not None and age > stale_lim * 4:
                return {
                    "available": False,
                    "reason": "quote_stale",
                    "reliability": "stale",
                    "age_sec": age,
                    "source": q.source,
                }
            # Research fallback — still estimated, separately labeled
            if "yahoo" in str(q.source or "").lower() or str(state).upper() == "FALLBACK":
                return {
                    "available": True,
                    "ltp": ltp,
                    "source": q.source,
                    "age_sec": age,
                    "reliability": "research_fallback",
                    "label": "estimated_unrealized_fallback_quote",
                }
            if age is not None and age <= stale_lim:
                return {
                    "available": True,
                    "ltp": ltp,
                    "source": q.source,
                    "age_sec": age,
                    "reliability": "live_quote",
                    "label": "estimated_unrealized_live_quote",
                }
        return {
            "available": False,
            "reason": f"feed_status={q.feed_status}",
            "reliability": "unavailable",
            "source": q.source,
            "age_sec": age,
        }
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {
            "available": False,
            "reason": sanitize_error_text(e),
            "reliability": "unavailable",
        }


def unrealized_for_trade(trade: dict[str, Any]) -> dict[str, Any]:
    if trade.get("status") != "open" or float(trade.get("quantity") or 0) <= 0:
        return {
            "available": False,
            "reason": "not_open",
            "estimated_unrealized_pnl": None,
            "label": None,
        }
    q = _reliable_quote(str(trade["instrument"]))
    if not q.get("available"):
        return {
            "available": False,
            "reason": q.get("reason") or "no_reliable_quote",
            "reliability": q.get("reliability"),
            "estimated_unrealized_pnl": None,
            "quote": q,
            "label": None,
            "note": "Unrealized P&L omitted — no reliable current quote",
        }
    ltp = float(q["ltp"])
    qty = float(trade["quantity"])
    entry = float(trade["entry_price"])
    if trade["direction"] == "LONG":
        pnl = (ltp - entry) * qty
    else:
        pnl = (entry - ltp) * qty
    return {
        "available": True,
        "estimated_unrealized_pnl": round(pnl, 2),
        "mark_price": ltp,
        "quantity": qty,
        "reliability": q["reliability"],
        "label": q["label"],
        "quote_source": q.get("source"),
        "quote_age_sec": q.get("age_sec"),
        "note": (
            "Estimated only from current quote — not a realized fill. "
            "Separately labeled; not mixed into book equity without this label."
        ),
    }


def capital_summary(*, path: Path | None = None) -> dict[str, Any]:
    ensure_schema(path)
    moves = list_capital_movements(path=path)
    starting = 0.0
    deposits = 0.0
    withdrawals = 0.0
    for m in moves:
        if m["kind"] == "starting_capital":
            starting += float(m["amount"])
        elif m["kind"] == "deposit":
            deposits += float(m["amount"])
        elif m["kind"] == "withdrawal":
            withdrawals += float(m["amount"])

    trades = list_trades(path=path)
    realized = 0.0
    fees = 0.0
    open_positions = []
    closed = []
    est_unrealized_sum = 0.0
    unrealized_any = False
    unrealized_missing = 0

    for t in trades:
        fees += float(t.get("fees_total") or 0)
        # realized_pnl on trade is gross exits − fees_total (entry+exit fees)
        realized += float(t.get("realized_pnl") or 0)
        if t["status"] == "open":
            u = unrealized_for_trade(t)
            t["unrealized"] = u
            open_positions.append(t)
            if u.get("available"):
                est_unrealized_sum += float(u["estimated_unrealized_pnl"])
                unrealized_any = True
            else:
                unrealized_missing += 1
        else:
            closed.append(t)

    # Book equity excludes unrealized; realized_pnl is already net of fees
    book_equity = round(starting + deposits - withdrawals + realized, 2)
    costs = round(fees, 2)

    return {
        "disclaimer": DISCLAIMER,
        "source_label": SOURCE_LABEL,
        "capital": {
            "starting_capital": round(starting, 2),
            "deposits": round(deposits, 2),
            "withdrawals": round(withdrawals, 2),
            "realized_pnl": round(realized, 2),
            "costs_fees_total": costs,
            "book_equity": book_equity,
            "formula": (
                "book_equity = starting_capital + deposits - withdrawals + realized_pnl; "
                "realized_pnl = sum(exit gross) − fees_total (entry+exit). "
                "estimated_unrealized is separate and not included in book_equity."
            ),
        },
        "estimated_unrealized": {
            "available": unrealized_any,
            "total": round(est_unrealized_sum, 2) if unrealized_any else None,
            "open_without_quote": unrealized_missing,
            "label": "estimated_unrealized_pnl_separate_from_book",
            "note": (
                "Shown only when a quote is available; never invented. "
                "Not included in book_equity."
            ),
        },
        "estimated_equity_mark": {
            "available": unrealized_any,
            "value": round(book_equity + est_unrealized_sum, 2) if unrealized_any else None,
            "label": "book_equity_plus_estimated_unrealized",
            "note": "Optional mark — still user-journal based, not a broker statement.",
        },
        "counts": {
            "open": len(open_positions),
            "closed": len(closed),
            "movements": len(moves),
        },
        "open_positions": open_positions,
        "closed_positions": closed,
        "movements": moves,
    }
