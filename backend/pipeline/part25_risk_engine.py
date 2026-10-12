from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

TUNING = {
    "atr_sl_mult": 1.0,
    "premium_sl_pct": 0.12,
    "min_confidence": 0.35,
    "min_confirming": 1,
    "capital_inr": 1_000_000.0,
}


def passes_risk_gate(rr: float | None, min_rr: float) -> bool:
    return rr is not None and rr >= min_rr


def position_size(capital: float, risk_frac: float, entry: float, sl: float, lot: int) -> int:
    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0 or lot <= 0 or risk_frac <= 0:
        return 0
    units = int((capital * risk_frac) // risk_per_unit)
    return max(0, (units // lot) * lot)


@register(25)
def run(ctx: PipelineContext) -> PartResult:
    ind = ctx.get("indicators") or {}
    spot = ctx.get("spot")
    atr_value = ind.get("atr") or (spot * 0.005 if spot else None)
    out = {
        "min_rr": 1.8,
        "atr_sl_distance": round(atr_value * TUNING["atr_sl_mult"], 2) if atr_value else None,
        **TUNING,
    }
    ctx.put("risk", out)
    return PartResult(25, "Risk Engine", output=out)
