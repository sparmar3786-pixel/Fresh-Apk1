"""TerminalEngine — deterministic 32-part per-index pipeline orchestrator.

The engine is source-agnostic: callers provide a snapshot provider. This keeps
broker credentials/session handling outside the strategy pipeline while still
supporting sync or async providers, memory, AI validation and broadcasting.
"""
from __future__ import annotations

import inspect
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import logging

logger = logging.getLogger(__name__)

from backend.app.models import MarketSnapshot
from backend.pipeline import loader  # noqa: F401
from backend.pipeline.base import REGISTRY
from backend.pipeline.context import PipelineContext, PipelineSettings

SnapshotProvider = Callable[[str], MarketSnapshot | None | Awaitable[MarketSnapshot | None]]
Broadcast = Callable[[str, Any], Awaitable[None]]


class TerminalEngine:
    def __init__(
        self,
        snapshot_provider: SnapshotProvider | None = None,
        *,
        indexes: list[str] | None = None,
        settings: PipelineSettings | None = None,
        memory: Any = None,
        ai: Any = None,
        broadcaster: Broadcast | None = None,
        advanced: bool = True,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.indexes = [x.upper() for x in (indexes or ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"])]
        self.settings = settings or PipelineSettings()
        self.memory = memory
        self.ai = ai
        self.broadcaster = broadcaster
        self.advanced = advanced
        self._running = False
        self._cycle = 0
        self._snapshots: dict[str, MarketSnapshot] = {}
        self._previous: dict[str, MarketSnapshot] = {}
        self._ticks: dict[str, deque] = {i: deque(maxlen=500) for i in self.indexes}
        self._last_bias: dict[str, float] = {}

    async def run_cycle(self) -> dict[str, Any]:
        self._cycle += 1
        out: dict[str, Any] = {}
        for index in self.indexes:
            try:
                result = await self._cycle_for_index(index)
                if result is not None:
                    out[index] = result
                    if self.broadcaster:
                        await self.broadcaster("decision", result.get("decision"))
            except Exception as exc:
                logger.exception("pipeline cycle failed for %s", index)
                out[index] = {"error": str(exc)}
        if self.broadcaster:
            await self.broadcaster("state", self.state_frame())
        return out

    async def _get_snapshot(self, index: str) -> MarketSnapshot | None:
        if self.snapshot_provider is None:
            return self._snapshots.get(index)
        value = self.snapshot_provider(index)
        return await value if inspect.isawaitable(value) else value

    async def _cycle_for_index(self, index: str) -> dict[str, Any] | None:
        snapshot = await self._get_snapshot(index)
        if snapshot is None:
            return None
        if not isinstance(snapshot, MarketSnapshot):
            snapshot = MarketSnapshot.model_validate(snapshot)

        ctx = PipelineContext(
            index=index,
            snapshot=snapshot,
            prev_snapshot=self._previous.get(index),
            ticks=list(self._ticks[index]),
            settings=self.settings,
            advanced=self.advanced,
        )
        ctx.price_history = list(snapshot.candles or []) + [snapshot.ltp]
        ctx.put("_memory", self.memory)
        ctx.put("_ai", self.ai)
        ctx.put("cross_index", dict(self._last_bias))
        adaptive = ctx.ensure_adaptive_intelligence()

        results = []
        for number in sorted(REGISTRY):
            result = REGISTRY[number](ctx)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)

        self._snapshots[index] = snapshot
        self._previous[index] = snapshot
        self._last_bias[index] = float((ctx.get("oi") or {}).get("bias", 0.0))

        decision = ctx.get("decision")
        payload = {
            "index": index,
            "cycle": self._cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adaptive_intelligence": adaptive,
            "ai_brief": ctx.get("ai_brief"),
            "decision": decision.model_dump(mode="json") if decision is not None else None,
            "parts": [r.__dict__ if hasattr(r, "__dict__") else r for r in results],
            "flags": list(ctx.flags),
        }
        return payload

    async def run_strategy_scan(self, index: str) -> dict[str, Any]:
        result = await self._cycle_for_index(index.upper())
        return result or {"error": f"no snapshot available for {index.upper()}"}

    def latest_snapshot(self, index: str) -> MarketSnapshot | None:
        return self._snapshots.get(index.upper())

    def state_frame(self) -> dict[str, Any]:
        return {
            "cycle": self._cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "advanced": self.advanced,
            "parts_registered": sorted(REGISTRY),
            "snapshots": {
                key: {
                    "spot": value.ltp,
                    "strikes": len({o.strike for o in value.options}),
                    "expiry": None,
                    "source": value.source,
                }
                for key, value in self._snapshots.items()
            },
        }

    async def run_forever(self, interval_seconds: float = 3.0, stop_event=None) -> None:
        self._running = True
        while self._running and (stop_event is None or not stop_event.is_set()):
            await self.run_cycle()
            if stop_event is not None:
                try:
                    await __import__("asyncio").wait_for(stop_event.wait(), timeout=max(0.1, interval_seconds))
                except TimeoutError:
                    pass
            else:
                await __import__("asyncio").sleep(max(0.1, interval_seconds))

    async def stop(self) -> None:
        self._running = False
