"""SQLite-backed strategy memory for observations and completed trades."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class StrategyMemory:
    def __init__(self, db_path: str = "data/strategy_memory.sqlite") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    index_name TEXT,
                    regime TEXT,
                    strategy TEXT,
                    strike REAL,
                    side TEXT,
                    entry REAL,
                    oi REAL,
                    premium REAL,
                    volume INTEGER,
                    iv REAL,
                    greeks TEXT,
                    expiry TEXT,
                    day_time TEXT,
                    result TEXT,
                    confidence REAL,
                    extra TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    strategy TEXT,
                    index_name TEXT,
                    side TEXT,
                    strike REAL,
                    entry REAL,
                    exit REAL,
                    r REAL,
                    result TEXT,
                    regime TEXT,
                    expiry TEXT,
                    strike_distance REAL,
                    day_time TEXT,
                    is_expiry INTEGER,
                    extra TEXT
                )
                """
            )

    def record_observation(self, rec: Dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO observations (
                    ts, index_name, regime, strategy, strike, side, entry,
                    oi, premium, volume, iv, greeks, expiry, day_time,
                    result, confidence, extra
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    rec.get("index"),
                    rec.get("regime"),
                    rec.get("strategy"),
                    rec.get("strike"),
                    rec.get("side"),
                    rec.get("entry"),
                    rec.get("oi"),
                    rec.get("premium"),
                    rec.get("volume"),
                    rec.get("iv"),
                    _j(rec.get("greeks")),
                    rec.get("expiry"),
                    rec.get("time"),
                    rec.get("result"),
                    rec.get("confidence"),
                    _j(rec.get("extra")),
                ),
            )

    def record_trade(self, trade: Dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trades (
                    ts, strategy, index_name, side, strike, entry, exit, r,
                    result, regime, expiry, strike_distance, day_time,
                    is_expiry, extra
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    trade.get("strategy_id"),
                    trade.get("index"),
                    trade.get("side"),
                    trade.get("strike"),
                    trade.get("entry"),
                    trade.get("exit"),
                    trade.get("r"),
                    trade.get("result"),
                    trade.get("regime"),
                    trade.get("expiry"),
                    trade.get("strike_distance"),
                    trade.get("time"),
                    1 if trade.get("is_expiry") else 0,
                    _j(trade.get("extra")),
                ),
            )

    def strategy_summary(self, index: str) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT r, result FROM trades WHERE index_name = ?", (index,)
            ).fetchall()
        rs = [float(row["r"]) for row in rows if row["r"] is not None]
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        return {
            "n": n,
            "win_rate": round(wins / n, 4) if n else None,
            "average_r": round(sum(rs) / n, 4) if n else None,
            "note": "sample statistic — not a forward promise",
        }

    def regime_behaviour(self, regime: Optional[str], index: str) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM observations WHERE regime IS ? AND index_name = ?",
                (regime, index),
            ).fetchone()
        return {
            "regime": regime,
            "index": index,
            "observations": int(row["c"] if row else 0),
        }

    def failure_patterns(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT strategy, index_name, regime, COUNT(*) AS losses
                FROM trades
                WHERE (r IS NOT NULL AND r <= 0)
                GROUP BY strategy, index_name, regime
                ORDER BY losses DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def trades_for_backtest(self, index: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM trades"
        args: tuple[Any, ...] = ()
        if index:
            query += " WHERE index_name = ?"
            args = (index,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["is_expiry"] = bool(item.get("is_expiry"))
            out.append(item)
        return out


def _j(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)
