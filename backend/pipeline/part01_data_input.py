from __future__ import annotations
from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext
@register(1)
def run(ctx: PipelineContext) -> PartResult:
    frame=[s.__dict__.copy() for s in ctx.normalize_strikes()]
    ctx.put("frame",frame); ctx.put("spot",ctx.snapshot.ltp); ctx.put("expiry",None); ctx.put("source",ctx.snapshot.source)
    if ctx.snapshot.timestamp: ctx.price_history.append(ctx.snapshot.ltp)
    ok=bool(frame) and ctx.snapshot.ltp is not None and ctx.snapshot.ltp>0
    res=PartResult(1,"Data Input",ok,data_gap=not ok,output={"strikes":len(frame),"spot":ctx.snapshot.ltp,"atm":ctx.get("atm_strike")})
    if not ok: res.notes.append("empty chain or missing spot")
    return res
