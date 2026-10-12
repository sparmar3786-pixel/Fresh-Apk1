from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(10)
def run(ctx):
    per={p["strike"]:p for p in (ctx.get("oi") or {}).get("per_strike",[])}; bull=sum(p.get("pe")=="SHORT BUILDUP" for p in per.values());bear=sum(p.get("pe")=="LONG BUILDUP" for p in per.values());out={"pe_bullish_count":bull,"pe_bearish_count":bear,"atm_pe_class":per.get(ctx.get("atm_strike"),{}).get("pe"),"score":round((bull-bear)*.5,3)};ctx.put("pe_engine",out);return PartResult(10,"PE Engine",output=out)
