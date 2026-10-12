from __future__ import annotations

from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext

@register(28)
def run(ctx: PipelineContext) -> PartResult:
    results = ctx.ensure_strategy_scan()
    kept, suppressed, seen = [], [], set()
    conflict = ctx.get("conflict") or {}
    for r in results:
        if not r.get("fired"):
            continue
        sid = r.get("strategy_id")
        if sid in seen:
            suppressed.append((sid, "duplicate"))
            continue
        seen.add(sid)
        if float(r.get("confidence") or 0) < 0.2:
            suppressed.append((sid, "weak"))
            continue
        if conflict.get("conflict") and abs(float(r.get("score") or 0)) < 0.5:
            suppressed.append((sid, "contradiction"))
            continue
        kept.append(sid)
    out = {"kept": kept, "suppressed": suppressed, "kept_count": len(kept), "suppressed_count": len(suppressed)}
    ctx.put("signal_quality", out)
    return PartResult(28, "Signal Quality Filter", output={"kept": len(kept), "suppressed": len(suppressed)})
