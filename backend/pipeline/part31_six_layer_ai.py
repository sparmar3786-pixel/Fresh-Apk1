from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(31)
async def run(ctx: PipelineContext) -> PartResult:
    adaptive = ctx.ensure_adaptive_intelligence()
    ai = ctx.get("_ai")
    if ai is None:
        ctx.put("ai", {"enabled": False, "reason": "AI client not attached"})
        return PartResult(31, "6-AI Validation", skipped=True, output={"brief_ready": True, "modules": len(adaptive.get("modules", {}))}, notes=["AI disabled"])
    try:
        verdict = await ai.validate(ctx)
        ctx.put("ai", verdict)
        return PartResult(31, "6-AI Validation", output={
            "layers": len(verdict.get("layers", [])),
            "wait_override": verdict.get("wait_override", False),
            "guarded": verdict.get("guard_triggered", False),
            "brief_modules": len(adaptive.get("modules", {})),
        })
    except Exception as exc:
        ctx.put("ai", {"enabled": True, "error": str(exc), "degraded": True})
        return PartResult(31, "6-AI Validation", ok=False, notes=[f"AI layer error (non-fatal): {exc}"])
