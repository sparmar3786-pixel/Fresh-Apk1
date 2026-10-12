from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(20)
def run(ctx):
    pa=ctx.get("price_action") or {};oi=ctx.get("oi") or {};pv=ctx.get("premium_volume") or {};bias=oi.get("bias",0);pb=pv.get("bias",0);tr={"bull_trap":bool(pa.get("bos") and bias<0),"bear_trap":bool(pa.get("choch") and bias>0),"false_oi_signal":abs(bias)>.3 and abs(pb)<.05,"false_volume_signal":pv.get("ce_vol_share",.5)>.9 and abs(pb)<.02,"exhaustion_reversal":abs(bias)>.5 and abs(pb)<.05};out={"traps":tr,"any_trap":any(tr.values())};ctx.put("trap",out);return PartResult(20,"Trap Engine",output=out)
