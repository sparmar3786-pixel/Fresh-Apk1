from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(29)
def run(ctx: PipelineContext) -> PartResult:
    memory = ctx.get("_memory")
    summary = {"available": False}
    if memory is not None:
        try:
            summary = dict(memory.strategy_summary(ctx.index))
            summary["available"] = True
        except Exception as exc:
            summary = {"available": False, "error": str(exc)}
    ctx.put("backtest", summary)
    return PartResult(29, "Backtest Engine", output={"available": summary.get("available", False)})
