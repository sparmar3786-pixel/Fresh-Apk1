from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from backend.app.models import MarketSnapshot

@dataclass
class PipelineStrike:
    strike: float
    is_atm: bool = False
    ce_ltp: float | None = None
    ce_oi: float | None = None
    ce_oi_change: float | None = None
    ce_volume: float | None = None
    ce_iv: float | None = None
    ce_delta: float | None = None
    ce_gamma: float | None = None
    ce_theta: float | None = None
    ce_vega: float | None = None
    ce_bid: float | None = None
    ce_ask: float | None = None
    ce_prev_ltp: float | None = None
    pe_ltp: float | None = None
    pe_oi: float | None = None
    pe_oi_change: float | None = None
    pe_volume: float | None = None
    pe_iv: float | None = None
    pe_delta: float | None = None
    pe_gamma: float | None = None
    pe_theta: float | None = None
    pe_vega: float | None = None
    pe_bid: float | None = None
    pe_ask: float | None = None
    pe_prev_ltp: float | None = None

@dataclass
class PipelineSettings:
    max_snapshot_age_sec: float = 15.0
    max_tick_age_sec: float = 15.0
    max_tick_jump_pct: float = 5.0

@dataclass
class PipelineContext:
    snapshot: MarketSnapshot
    prev_snapshot: MarketSnapshot | None = None
    ticks: list[Any] = field(default_factory=list)
    settings: PipelineSettings = field(default_factory=PipelineSettings)
    data: dict[str, Any] = field(default_factory=dict)
    price_history: list[float] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    advanced: bool = False
    index: str = ""

    def get(self, key: str, default=None): return self.data.get(key, default)
    def put(self, key: str, value: Any): self.data[key] = value
    def flag(self, value: str):
        if value not in self.flags: self.flags.append(value)

    def ensure_adaptive_intelligence(self) -> dict[str, Any]:
        cached = self.get("_adaptive_intelligence")
        if cached is not None:
            return cached
        from backend.pipeline.adaptive_intelligence import evaluate_adaptive_intelligence
        result = evaluate_adaptive_intelligence(
            self.snapshot,
            self.prev_snapshot,
            self.get("cross_index") or {},
            self.get("_memory"),
        )
        self.put("_adaptive_intelligence", result)
        self.put("adaptive", result)
        self.put("ai_brief", result["ai_brief"])
        if result["decision_vote"].get("guard"):
            self.flag(result["decision_vote"]["guard"])
        return result

    def ensure_strategy_scan(self) -> list[dict[str, Any]]:
        cached = self.get("_strategy_scan")
        if cached is not None:
            return cached
        from backend.app.strategies import analyze
        result = analyze(self.snapshot, stale_after_seconds=int(self.settings.max_snapshot_age_sec))
        rows = []
        if result.decision.value in {"CALL BUY", "PUT BUY"} and not result.guards:
            side = "CE" if result.decision.value == "CALL BUY" else "PE"
            rows.append({
                "strategy_id": "S001",
                "fired": True,
                "side": side,
                "score": 1.0 if side == "CE" else -1.0,
                "confidence": min(1.0, float(result.confidence) / 100.0),
                "reason": "deterministic strategy engine",
            })
        advanced_context = dict(self.data)
        advanced_context["snapshot"] = self.snapshot
        if self.advanced:
            from backend.strategies.advanced_modules import run_advanced
            for row in run_advanced(advanced_context, enabled=True):
                rows.append(row)
        self.put("_strategy_scan", rows)
        return rows

    def normalize_strikes(self) -> list[PipelineStrike]:
        grouped: dict[float, PipelineStrike] = {}
        for o in self.snapshot.options:
            row = grouped.setdefault(o.strike, PipelineStrike(strike=o.strike))
            if o.side == "CE":
                row.ce_ltp, row.ce_oi, row.ce_oi_change, row.ce_volume = o.ltp, o.oi, o.oi_change, o.volume
                row.ce_iv, row.ce_delta, row.ce_gamma, row.ce_theta, row.ce_vega = o.iv, o.delta, o.gamma, o.theta, o.vega
                row.ce_bid, row.ce_ask = getattr(o, "bid", None), getattr(o, "ask", None)
            elif o.side == "PE":
                row.pe_ltp, row.pe_oi, row.pe_oi_change, row.pe_volume = o.ltp, o.oi, o.oi_change, o.volume
                row.pe_iv, row.pe_delta, row.pe_gamma, row.pe_theta, row.pe_vega = o.iv, o.delta, o.gamma, o.theta, o.vega
                row.pe_bid, row.pe_ask = getattr(o, "bid", None), getattr(o, "ask", None)
        atm = self.snapshot.ltp
        if grouped:
            nearest = min(grouped, key=lambda k: abs(k - atm))
            for row in grouped.values(): row.is_atm = row.strike == nearest
            self.put("atm_strike", self.snapshot.atm_strike if hasattr(self.snapshot, "atm_strike") else nearest)
        frame = list(sorted(grouped.values(), key=lambda x: x.strike))
        self.put("frame", [row.__dict__.copy() for row in frame])
        return frame
