from __future__ import annotations

from threading import Lock
from time import time
from typing import Any


class MarketStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ticks: dict[str, dict[str, Any]] = {}
        self._update_count = 0
        self._last_update_at: float | None = None

    def update(self, tick: dict[str, Any]) -> None:
        token = str(tick.get("token", ""))
        if not token:
            return
        now = time()
        with self._lock:
            self._ticks[token] = {**tick, "received_at": now}
            self._update_count += 1
            self._last_update_at = now

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "unique_tokens": len(self._ticks),
                "update_count": self._update_count,
                "last_update_at": self._last_update_at,
                "last_update_age_seconds": round(time() - self._last_update_at, 1) if self._last_update_at is not None else None,
            }

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._ticks.values())

    def get(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            return self._ticks.get(token)
