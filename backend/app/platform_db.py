"""Platform persistence: users, sessions, instruments, append-only signals, LLM vault, audit."""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.crypto_secrets import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

PLATFORM_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('customer','admin')),
  display_name TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS instruments (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  name TEXT,
  category TEXT NOT NULL CHECK(category IN ('intraday','swing','commodity')),
  market TEXT DEFAULT 'NSE',
  is_active INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(symbol, category)
);

CREATE TABLE IF NOT EXISTS signal_records (
  id TEXT PRIMARY KEY,
  instrument_id TEXT REFERENCES instruments(id),
  symbol TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('intraday','swing','commodity')),
  direction TEXT NOT NULL CHECK(direction IN ('buy','sell','none')),
  timeframe TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft','published','expired','revised')),
  created_at TEXT NOT NULL,
  expires_at TEXT,
  published_at TEXT,
  rationale TEXT,
  evidence_json TEXT,
  provenance_json TEXT,
  risk_notes TEXT,
  methodology_id TEXT,
  data_mode TEXT NOT NULL DEFAULT 'demo' CHECK(data_mode IN ('live','delayed','stale','demo')),
  created_by TEXT,
  supersedes_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signal_records(symbol, category);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signal_records(status, category);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signal_records(created_at);

CREATE TABLE IF NOT EXISTS llm_secrets (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT,
  ciphertext TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  actor_user_id TEXT,
  action TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  detail_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PlatformDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(PLATFORM_SCHEMA)
            conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    # ---- users / sessions ----
    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str = "customer",
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        uid = str(uuid.uuid4())
        now = _utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(id, email, password_hash, role, display_name, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (uid, email.strip().lower(), password_hash, role, display_name, now, now),
            )
            conn.commit()
        return self.get_user(uid)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email=? COLLATE NOCASE",
                (email.strip().lower(),),
            ).fetchone()
        return dict(row) if row else None

    def create_session(self, user_id: str, ttl_hours: int = 72) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=ttl_hours)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(token, user_id, created_at, expires_at, last_seen_at)
                VALUES (?,?,?,?,?)
                """,
                (
                    token,
                    user_id,
                    now.replace(microsecond=0).isoformat(),
                    exp.replace(microsecond=0).isoformat(),
                    now.replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
        return token

    def get_session_user(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        now = _utcnow()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token=? AND s.expires_at > ? AND u.is_active=1
                """,
                (token, now),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE token=?",
                    (now, token),
                )
                conn.commit()
        return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()

    # ---- instruments ----
    def upsert_instrument(
        self,
        symbol: str,
        category: str,
        name: Optional[str] = None,
        market: str = "NSE",
        is_active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _utcnow()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM instruments WHERE symbol=? AND category=?",
                (symbol.upper(), category),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE instruments SET name=?, market=?, is_active=?, metadata_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        name,
                        market,
                        1 if is_active else 0,
                        json.dumps(metadata or {}),
                        now,
                        existing["id"],
                    ),
                )
                iid = existing["id"]
            else:
                iid = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO instruments(
                      id, symbol, name, category, market, is_active, metadata_json, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        iid,
                        symbol.upper(),
                        name,
                        category,
                        market,
                        1 if is_active else 0,
                        json.dumps(metadata or {}),
                        now,
                        now,
                    ),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM instruments WHERE id=?", (iid,)).fetchone()
        return self._instrument_row(row)

    def list_instruments(
        self, category: Optional[str] = None, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        q = "SELECT * FROM instruments WHERE 1=1"
        params: list[Any] = []
        if category:
            q += " AND category=?"
            params.append(category)
        if active_only:
            q += " AND is_active=1"
        q += " ORDER BY category, symbol"
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._instrument_row(r) for r in rows]

    @staticmethod
    def _instrument_row(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            d["metadata"] = {}
        d["is_active"] = bool(d.get("is_active"))
        return d

    # ---- signals (append-only) ----
    def publish_signal(self, payload: Dict[str, Any], actor_id: Optional[str] = None) -> Dict[str, Any]:
        sid = str(uuid.uuid4())
        now = _utcnow()
        status = payload.get("status") or "published"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO signal_records(
                  id, instrument_id, symbol, category, direction, timeframe, status,
                  created_at, expires_at, published_at, rationale, evidence_json,
                  provenance_json, risk_notes, methodology_id, data_mode, created_by,
                  supersedes_id, revision
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    payload.get("instrument_id"),
                    payload["symbol"].upper(),
                    payload["category"],
                    payload["direction"],
                    payload["timeframe"],
                    status,
                    now,
                    payload.get("expires_at"),
                    now if status == "published" else None,
                    payload.get("rationale"),
                    json.dumps(payload.get("evidence") or {}),
                    json.dumps(payload.get("provenance") or {}),
                    payload.get("risk_notes"),
                    payload.get("methodology_id") or "baseline_v1",
                    payload.get("data_mode") or "demo",
                    actor_id,
                    payload.get("supersedes_id"),
                    int(payload.get("revision") or 1),
                ),
            )
            conn.commit()
        self.audit(actor_id, "signal.publish", "signal", sid, {"symbol": payload["symbol"]})
        return self.get_signal(sid)  # type: ignore[return-value]

    def revise_signal(
        self, prior_id: str, updates: Dict[str, Any], actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        prior = self.get_signal(prior_id)
        if not prior:
            raise KeyError("signal not found")
        # Mark prior as revised (status change only — row kept)
        with self.connect() as conn:
            conn.execute(
                "UPDATE signal_records SET status='revised' WHERE id=? AND status!='revised'",
                (prior_id,),
            )
            conn.commit()
        new_payload = {
            "instrument_id": prior.get("instrument_id"),
            "symbol": prior["symbol"],
            "category": prior["category"],
            "direction": updates.get("direction", prior["direction"]),
            "timeframe": updates.get("timeframe", prior["timeframe"]),
            "status": updates.get("status", "published"),
            "expires_at": updates.get("expires_at", prior.get("expires_at")),
            "rationale": updates.get("rationale", prior.get("rationale")),
            "evidence": updates.get("evidence", prior.get("evidence")),
            "provenance": updates.get("provenance", prior.get("provenance")),
            "risk_notes": updates.get("risk_notes", prior.get("risk_notes")),
            "methodology_id": updates.get("methodology_id", prior.get("methodology_id")),
            "data_mode": updates.get("data_mode", prior.get("data_mode")),
            "supersedes_id": prior_id,
            "revision": int(prior.get("revision") or 1) + 1,
        }
        return self.publish_signal(new_payload, actor_id=actor_id)

    def expire_due_signals(self) -> int:
        now = _utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE signal_records
                SET status='expired'
                WHERE status='published' AND expires_at IS NOT NULL AND expires_at < ?
                """,
                (now,),
            )
            conn.commit()
            return cur.rowcount

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM signal_records WHERE id=?", (signal_id,)
            ).fetchone()
        return self._signal_row(row) if row else None

    def list_signals(
        self,
        category: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        include_history: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self.expire_due_signals()
        q = "SELECT * FROM signal_records WHERE 1=1"
        params: list[Any] = []
        if category:
            q += " AND category=?"
            params.append(category)
        if symbol:
            q += " AND symbol=?"
            params.append(symbol.upper())
        if status:
            q += " AND status=?"
            params.append(status)
        elif not include_history:
            q += " AND status IN ('published','draft')"
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(min(limit, 500))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._signal_row(r) for r in rows]

    @staticmethod
    def _signal_row(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for key, out in (("evidence_json", "evidence"), ("provenance_json", "provenance")):
            raw = d.pop(key, None)
            try:
                d[out] = json.loads(raw or "{}")
            except json.JSONDecodeError:
                d[out] = {}
        return d

    # ---- LLM vault ----
    def set_llm_secret(
        self, user_id: str, provider: str, api_key: str, model: Optional[str] = None
    ) -> Dict[str, Any]:
        now = _utcnow()
        cipher = encrypt_secret(api_key)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_secrets(user_id, provider, model, ciphertext, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                  provider=excluded.provider,
                  model=excluded.model,
                  ciphertext=excluded.ciphertext,
                  updated_at=excluded.updated_at
                """,
                (user_id, provider, model, cipher, now),
            )
            conn.commit()
        self.audit(user_id, "llm_secret.upsert", "llm_secrets", user_id, {"provider": provider})
        return {"configured": True, "provider": provider, "model": model, "updated_at": now}

    def get_llm_secret_meta(self, user_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT provider, model, updated_at FROM llm_secrets WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return {"configured": False, "provider": None, "model": None}
        return {
            "configured": True,
            "provider": row["provider"],
            "model": row["model"],
            "updated_at": row["updated_at"],
        }

    def get_llm_api_key(self, user_id: str) -> Optional[tuple[str, str, Optional[str]]]:
        """Returns (provider, plaintext_key, model) or None. Never expose via HTTP."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT provider, model, ciphertext FROM llm_secrets WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return row["provider"], decrypt_secret(row["ciphertext"]), row["model"]

    def delete_llm_secret(self, user_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM llm_secrets WHERE user_id=?", (user_id,))
            conn.commit()
        self.audit(user_id, "llm_secret.delete", "llm_secrets", user_id, {})

    # ---- audit / settings ----
    def audit(
        self,
        actor_user_id: Optional[str],
        action: str,
        entity_type: Optional[str],
        entity_id: Optional[str],
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log(id, actor_user_id, action, entity_type, entity_id, detail_json, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    actor_user_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(detail or {}),
                    _utcnow(),
                ),
            )
            conn.commit()

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
                (min(limit, 500),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = json.loads(d.pop("detail_json") or "{}")
            except json.JSONDecodeError:
                d["detail"] = {}
            out.append(d)
        return out

    def set_setting(self, key: str, value: Any, actor_id: Optional[str] = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value_json, updated_at, updated_by)
                VALUES (?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  value_json=excluded.value_json,
                  updated_at=excluded.updated_at,
                  updated_by=excluded.updated_by
                """,
                (key, json.dumps(value), _utcnow(), actor_id),
            )
            conn.commit()
        self.audit(actor_id, "settings.update", "app_settings", key, {})

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default
