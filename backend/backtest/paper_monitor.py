"""Paper-trading ledger and monitoring utilities.

This module records simulated fills only; it never sends broker orders.
Trade P&L is net of explicit per-trade costs and slippage supplied in the
same R units as the trade's gross result.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable

from backend.backtest.engine import compute_metrics


@dataclass
class PaperTrade:
    trade_id: str
    strategy_id: str
    index: str
    side: str
    entry_time: str
    exit_time: str | None
    gross_r: float | None
    slippage_r: float
    transaction_cost_r: float
    regime: str
    status: str = "OPEN"
    notes: str = ""

    @property
    def net_r(self) -> float | None:
        if self.gross_r is None:
            return None
        return float(self.gross_r) - float(self.slippage_r) - float(self.transaction_cost_r)


class PaperTradeMonitor:
    """Thread-safe in-memory paper ledger; inject durable storage if needed."""

    def __init__(self, max_open_trades: int = 5, max_daily_loss_r: float = 3.0,
                 max_consecutive_losses: int = 3, storage_path: str | None = None) -> None:
        self.max_open_trades = max(1, int(max_open_trades))
        self.max_daily_loss_r = abs(float(max_daily_loss_r))
        self.max_consecutive_losses = max(1, int(max_consecutive_losses))
        self.storage_path = storage_path
        self._trades: dict[str, PaperTrade] = {}
        self._lock = RLock()
        if self.storage_path:
            self._load()

    def open_trade(self, trade_id: str, strategy_id: str, index: str, side: str,
                   regime: str, *, slippage_r: float = 0.0,
                   transaction_cost_r: float = 0.0, notes: str = "",
                   timestamp: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            if trade_id in self._trades:
                raise ValueError("duplicate trade_id")
            if self.kill_switch()["blocked"]:
                raise RuntimeError("paper trading blocked by risk monitor")
            if sum(t.status == "OPEN" for t in self._trades.values()) >= self.max_open_trades:
                raise RuntimeError("max open paper trades reached")
            now = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
            trade = PaperTrade(trade_id, strategy_id, index, side, now, None, None,
                               max(0.0, float(slippage_r)), max(0.0, float(transaction_cost_r)),
                               regime, notes=notes)
            self._trades[trade_id] = trade
            self._persist()
            return asdict(trade) | {"net_r": None}

    def close_trade(self, trade_id: str, gross_r: float, *,
                    timestamp: datetime | None = None, notes: str = "") -> dict[str, Any]:
        with self._lock:
            trade = self._trades.get(trade_id)
            if trade is None:
                raise KeyError("unknown paper trade")
            if trade.status != "OPEN":
                raise ValueError("paper trade already closed")
            now = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
            trade.gross_r = float(gross_r)
            trade.exit_time = now
            trade.status = "CLOSED"
            if notes:
                trade.notes = notes
            self._persist()
            return asdict(trade) | {"net_r": trade.net_r}

    def trades(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(t) | {"net_r": t.net_r} for t in self._trades.values()]

    def kill_switch(self) -> dict[str, Any]:
        with self._lock:
            closed = [t for t in self._trades.values() if t.status == "CLOSED"]
            today = datetime.now(timezone.utc).date().isoformat()
            todays = [t for t in closed if t.exit_time and t.exit_time[:10] == today]
            daily_net = sum(t.net_r or 0.0 for t in todays)
            streak = 0
            for trade in reversed(closed):
                if trade.net_r is not None and trade.net_r < 0:
                    streak += 1
                else:
                    break
            reasons = []
            if daily_net <= -self.max_daily_loss_r:
                reasons.append("MAX_DAILY_LOSS")
            if streak >= self.max_consecutive_losses:
                reasons.append("MAX_CONSECUTIVE_LOSSES")
            return {"blocked": bool(reasons), "reasons": reasons,
                    "daily_net_r": round(daily_net, 4), "consecutive_losses": streak}

    def report(self) -> dict[str, Any]:
        with self._lock:
            closed = [t for t in self._trades.values() if t.status == "CLOSED"]
            rows = [{
                "r": t.net_r, "strategy_id": t.strategy_id, "index": t.index,
                "side": t.side, "regime": t.regime, "time": t.entry_time[11:16],
            } for t in closed if t.net_r is not None]
            return {
                "mode": "PAPER_ONLY",
                "open_trades": sum(t.status == "OPEN" for t in self._trades.values()),
                "closed_trades": len(rows),
                "net_metrics": compute_metrics(rows),
                "regime_wise": self._group(rows, "regime"),
                "strategy_wise": self._group(rows, "strategy_id"),
                "risk": self.kill_switch(),
                "persistence": "sqlite" if self.storage_path else "in_memory",
            }

    @staticmethod
    def _group(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(str(row.get(key, "na")), []).append(row)
        return {k: compute_metrics(v) for k, v in groups.items()}

    def _load(self) -> None:
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS paper_trades (trade_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, index_name TEXT NOT NULL, side TEXT NOT NULL, entry_time TEXT NOT NULL, exit_time TEXT, gross_r REAL, slippage_r REAL NOT NULL, transaction_cost_r REAL NOT NULL, regime TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL)")
            for row in conn.execute("SELECT * FROM paper_trades"):
                trade = PaperTrade(trade_id=row[0], strategy_id=row[1], index=row[2], side=row[3], entry_time=row[4], exit_time=row[5], gross_r=row[6], slippage_r=row[7], transaction_cost_r=row[8], regime=row[9], status=row[10], notes=row[11])
                self._trades[trade.trade_id] = trade

    def _persist(self) -> None:
        if not self.storage_path:
            return
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS paper_trades (trade_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, index_name TEXT NOT NULL, side TEXT NOT NULL, entry_time TEXT NOT NULL, exit_time TEXT, gross_r REAL, slippage_r REAL NOT NULL, transaction_cost_r REAL NOT NULL, regime TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL)")
            conn.executemany("INSERT OR REPLACE INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                (t.trade_id, t.strategy_id, t.index, t.side, t.entry_time, t.exit_time, t.gross_r, t.slippage_r, t.transaction_cost_r, t.regime, t.status, t.notes)
                for t in self._trades.values()
            ])
