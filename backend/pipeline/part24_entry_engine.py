from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(24)
def run(ctx):
    f=ctx.get("frame") or [];atm=ctx.get("atm_strike");bias=(ctx.get("oi") or {}).get("bias",0);side="CE" if bias>=0 else "PE";row=next((x for x in f if x["strike"]==atm),None)
    if row is None:ctx.put("entry",{"data_gap":True});return PartResult(24,"Entry Engine",data_gap=True,notes=["ATM option missing"])
    l=row.get(side.lower()+"_ltp");ask=row.get(side.lower()+"_ask");out={"side":side,"strike":row["strike"],"entry":l,"ask":ask,"entry_type":"confirmation" if abs(bias)>.3 else "early","chase":bool(l and ask and ask>l*1.01)};ctx.put("entry",out);gap=l is None;return PartResult(24,"Entry Engine",data_gap=gap,output=out,notes=["entry price missing"] if gap else [])
