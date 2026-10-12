from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DB_PATH = Path(os.getenv("DATA_DIR", "/data")) / "fresh_algo_secure.db"


def _fernet() -> Fernet:
    key = os.getenv("APP_FERNET_KEY", "").strip()
    if not key:
        raise RuntimeError("APP_FERNET_KEY is missing. Set it in Railway Variables.")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("APP_FERNET_KEY is not a valid Fernet key.") from exc


def _enc(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def _dec(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored secret cannot be decrypted. APP_FERNET_KEY changed."
        ) from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_store() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_credentials (
                device_id TEXT PRIMARY KEY,
                openai_key_enc TEXT,
                model TEXT NOT NULL DEFAULT 'gpt-5',
                exa_key_enc TEXT,
                tavily_key_enc TEXT,
                brave_key_enc TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                device_id TEXT NOT NULL,
                index_name TEXT NOT NULL,
                snapshot_json_enc TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (device_id, index_name)
            );

            CREATE TABLE IF NOT EXISTS angel_sessions (
                device_id TEXT PRIMARY KEY,
                client_code TEXT NOT NULL,
                api_key_enc TEXT NOT NULL,
                pin_enc TEXT,
                jwt_enc TEXT NOT NULL,
                refresh_enc TEXT,
                feed_enc TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )

        # Existing persistent Railway volumes may have older schemas. Migrate
        # in place so saved sessions/AI keys survive deploys without data loss.
        ai_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(ai_credentials)").fetchall()
        }
        for column in ("exa_key_enc", "tavily_key_enc", "brave_key_enc"):
            if column not in ai_columns:
                conn.execute(f"ALTER TABLE ai_credentials ADD COLUMN {column} TEXT")

        angel_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(angel_sessions)").fetchall()
        }
        if "pin_enc" not in angel_columns:
            conn.execute("ALTER TABLE angel_sessions ADD COLUMN pin_enc TEXT")


def _existing(conn: sqlite3.Connection, table: str, device_id: str):
    # Table names are internal constants; device_id remains a parameterized value.
    return conn.execute(
        f"SELECT * FROM {table} WHERE device_id = ?", (device_id,)
    ).fetchone()


def save_ai(
    device_id: str,
    *,
    openai_key: str | None,
    model: str,
    exa_key: str | None = None,
    tavily_key: str | None = None,
    brave_key: str | None = None,
) -> None:
    """Update supplied credentials while preserving previously stored blank fields."""
    with connect() as conn:
        old = _existing(conn, "ai_credentials", device_id)

        def keep_or_encrypt(new: str | None, column: str):
            value = (new or "").strip()
            return _enc(value) if value else (old[column] if old else None)

        values = (
            device_id,
            keep_or_encrypt(openai_key, "openai_key_enc"),
            model.strip() or (old["model"] if old else "gpt-5"),
            keep_or_encrypt(exa_key, "exa_key_enc"),
            keep_or_encrypt(tavily_key, "tavily_key_enc"),
            keep_or_encrypt(brave_key, "brave_key_enc"),
            _now(),
        )
        conn.execute(
            """
            INSERT INTO ai_credentials
              (device_id, openai_key_enc, model, exa_key_enc, tavily_key_enc,
               brave_key_enc, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
              openai_key_enc=excluded.openai_key_enc,
              model=excluded.model,
              exa_key_enc=excluded.exa_key_enc,
              tavily_key_enc=excluded.tavily_key_enc,
              brave_key_enc=excluded.brave_key_enc,
              updated_at=excluded.updated_at
            """,
            values,
        )


def load_ai(device_id: str):
    with connect() as conn:
        row = _existing(conn, "ai_credentials", device_id)
    if not row:
        return None
    return {
        "openai_api_key": _dec(row["openai_key_enc"]),
        "openai_model": row["model"] or "gpt-5",
        "exa_api_key": _dec(row["exa_key_enc"]),
        "tavily_api_key": _dec(row["tavily_key_enc"]),
        "brave_search_api_key": _dec(row["brave_key_enc"]),
    }


def save_angel_session(
    device_id: str,
    *,
    client_code: str,
    api_key: str,
    pin: str | None = None,
    jwt: str,
    refresh: str | None,
    feed: str | None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO angel_sessions
              (device_id, client_code, api_key_enc, pin_enc, jwt_enc, refresh_enc,
               feed_enc, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
              client_code=excluded.client_code,
              api_key_enc=excluded.api_key_enc,
              pin_enc=COALESCE(excluded.pin_enc, angel_sessions.pin_enc),
              jwt_enc=excluded.jwt_enc,
              refresh_enc=excluded.refresh_enc,
              feed_enc=excluded.feed_enc,
              updated_at=excluded.updated_at
            """,
            (
                device_id,
                client_code.strip(),
                _enc(api_key.strip()),
                _enc(pin.strip() if pin else None),
                _enc(jwt),
                _enc(refresh),
                _enc(feed),
                _now(),
            ),
        )


def load_angel_session(device_id: str):
    with connect() as conn:
        row = _existing(conn, "angel_sessions", device_id)
    if not row:
        return None
    return {
        "client_code": row["client_code"],
        "api_key": _dec(row["api_key_enc"]),
        "pin": _dec(row["pin_enc"]) if "pin_enc" in row.keys() else None,
        "jwt": _dec(row["jwt_enc"]),
        "refresh": _dec(row["refresh_enc"]),
        "feed": _dec(row["feed_enc"]),
        "updated_at": row["updated_at"],
    }


def delete_angel_session(device_id: str) -> None:
    """Remove a rejected/stale saved Angel session for this device."""
    with connect() as conn:
        conn.execute("DELETE FROM angel_sessions WHERE device_id = ?", (device_id,))


def angel_session_status(device_id: str):
    session = load_angel_session(device_id)
    if not session:
        return None
    return {
        "client_code": session["client_code"],
        "updated_at": session["updated_at"],
        "has_jwt": bool(session["jwt"]),
        "has_feed_token": bool(session["feed"]),
        "has_saved_api_key": bool(session.get("api_key")),
        "has_saved_pin": bool(session.get("pin")),
        "has_refresh_token": bool(session["refresh"]),
    }


def save_market_snapshots(device_id: str, snapshots: dict[str, dict]) -> None:
    if not snapshots:
        return
    with connect() as conn:
        for index_name, snapshot in snapshots.items():
            conn.execute(
                """
                INSERT INTO market_snapshots
                  (device_id, index_name, snapshot_json_enc, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(device_id, index_name) DO UPDATE SET
                  snapshot_json_enc=excluded.snapshot_json_enc,
                  updated_at=excluded.updated_at
                """,
                (
                    device_id,
                    index_name.upper(),
                    _enc(json.dumps(snapshot, separators=(",", ":"))),
                    _now(),
                ),
            )


def load_market_snapshots(device_id: str) -> dict[str, dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT index_name, snapshot_json_enc FROM market_snapshots WHERE device_id = ?",
            (device_id,),
        ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        raw = _dec(row["snapshot_json_enc"])
        if not raw:
            continue
        try:
            result[row["index_name"]] = json.loads(raw)
        except json.JSONDecodeError:
            continue
    return result
