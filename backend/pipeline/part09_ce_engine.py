from __future__ import annotations
from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext
@register(9)
def run(ctx):
    per={p["strike"]:p for p in (ctx.get("oi") or {}).get("per_strike",[])}; up=dn=0
    for p in per.values(): up+=p.get("ce")=="LONG BUILDUP"; dn+=p.get("ce")=="SHORT BUILDUP"
    out={"ce_bullish_count":up,"ce_bearish_count":dn,"atm_ce_class":per.get(ctx.get("atm_strike"),{}).get("ce"),"score":round((up-dn)*.5,3)};ctx.put("ce_engine",out);return PartResult(9,"CE Engine",output=out)
