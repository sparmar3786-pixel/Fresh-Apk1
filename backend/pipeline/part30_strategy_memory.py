from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(30)
def run(ctx: PipelineContext) -> PartResult:
    memory = ctx.get("_memory")
    if memory is None:
        ctx.put("memory", {"available": False})
        return PartResult(30, "Strategy Memory", output={"available": False})

    greeks = ctx.get("greeks") or {}
    entry = ctx.get("entry") or {}
    pv = ctx.get("premium_volume") or {}
    record = {
        "index": ctx.index,
        "regime": ctx.get("regime"),
        "strike": ctx.get("atm_strike"),
        "side": entry.get("side"),
        "entry": entry.get("entry"),
        "oi": (ctx.get("oi") or {}).get("bias"),
        "premium": pv.get("bias"),
        "volume": pv.get("total_volume"),
        "iv": greeks.get("atm_ce_iv") or greeks.get("avg_ce_iv"),
        "greeks": greeks,
        "expiry": (ctx.get("expiry") or {}).get("expiry"),
        "time": (ctx.get("time") or {}).get("ist_time"),
        "confidence": ctx.get("confidence"),
    }
    try:
        memory.record_observation(record)
        behaviour = memory.regime_behaviour(ctx.get("regime"), ctx.index)
        ctx.put("memory", {"available": True, "regime_behaviour": behaviour})
    except Exception as exc:
        ctx.put("memory", {"available": False, "error": str(exc)})
    return PartResult(30, "Strategy Memory", output={"available": ctx.get("memory", {}).get("available", False)})
