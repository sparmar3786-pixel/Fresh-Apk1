from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(26)
def run(ctx: PipelineContext) -> PartResult:
    dq = ctx.get("dq")
    oi = ctx.get("oi") or {}
    trap = ctx.get("trap") or {}
    base = 0.30 if (dq is None or getattr(dq, "passed", True)) else 0.0
    base += min(0.35, abs(float(oi.get("bias", 0.0))))
    scan = ctx.ensure_strategy_scan()
    fired = [r for r in scan if r.get("fired")]
    base += min(0.20, len(fired) * 0.02)
    if ctx.get("regime") not in (None, "UNCERTAIN"):
        base += 0.05
    if trap.get("any_trap"):
        base -= 0.15
    confidence = max(0.0, min(1.0, base))
    ctx.put("confidence", round(confidence, 4))
    return PartResult(26, "Confidence Engine", output={
        "confidence": round(confidence, 4),
        "confirming": len(fired),
        "note": "heuristic score, not a probability/win rate",
    })
