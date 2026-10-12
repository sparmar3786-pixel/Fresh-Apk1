from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(27)
def run(ctx: PipelineContext) -> PartResult:
    results = [r for r in ctx.ensure_strategy_scan() if r.get("fired")]
    call_score = sum(float(r.get("score") or 0) for r in results if r.get("side") == "CE")
    put_score = sum(abs(float(r.get("score") or 0)) for r in results if r.get("side") == "PE")
    conflict = bool(call_score and put_score and abs(call_score - put_score) < 1.0)
    out = {
        "call_score": round(call_score, 4),
        "put_score": round(put_score, 4),
        "net_score": round(call_score - put_score, 4),
        "conflict": conflict,
    }
    ctx.put("conflict", out)
    return PartResult(27, "Strategy Conflict Engine", output=out)
