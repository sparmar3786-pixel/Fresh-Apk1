from __future__ import annotations
from typing import Optional
from backend.app.models import OISignal
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
_BIAS={"CE":{OISignal.LONG_BUILDUP:1,OISignal.SHORT_COVERING:1,OISignal.SHORT_BUILDUP:-1,OISignal.LONG_UNWINDING:-1,OISignal.NEUTRAL:0},"PE":{OISignal.LONG_BUILDUP:-1,OISignal.SHORT_COVERING:-1,OISignal.SHORT_BUILDUP:1,OISignal.LONG_UNWINDING:1,OISignal.NEUTRAL:0}}
def classify_oi(premium_change:Optional[float],oi_change:Optional[float],eps=1e-9):
    if premium_change is None or oi_change is None:return OISignal.NEUTRAL
    if premium_change>eps and oi_change>eps:return OISignal.LONG_BUILDUP
    if premium_change<-eps and oi_change>eps:return OISignal.SHORT_BUILDUP
    if premium_change>eps and oi_change<-eps:return OISignal.SHORT_COVERING
    if premium_change<-eps and oi_change<-eps:return OISignal.LONG_UNWINDING
    return OISignal.NEUTRAL
@register(6)
def run(ctx):
    prev={o.strike:o for o in (ctx.prev_snapshot.options if ctx.prev_snapshot else [])}; rows=[];agg=0;weight=0;counts={c.value:0 for c in OISignal}
    for st in ctx.get("frame") or []:
        for side in ("CE","PE"):
            p=st[f"{side.lower()}_ltp"]; old=(prev.get(st["strike"]).ltp if prev.get(st["strike"]) and prev.get(st["strike"]).side==side else st[f"{side.lower()}_prev_ltp"]); cls=classify_oi(None if p is None or old is None else p-old,st[f"{side.lower()}_oi_change"]);counts[cls.value]+=1;agg+=_BIAS[side][cls]*(st[f"{side.lower()}_oi"] or 0);weight+=st[f"{side.lower()}_oi"] or 0
        rows.append({"strike":st["strike"],"ce":classify_oi(None if st["ce_ltp"] is None or st["ce_prev_ltp"] is None else st["ce_ltp"]-st["ce_prev_ltp"],st["ce_oi_change"]).value,"pe":classify_oi(None if st["pe_ltp"] is None or st["pe_prev_ltp"] is None else st["pe_ltp"]-st["pe_prev_ltp"],st["pe_oi_change"]).value,"ce_oi_change":st["ce_oi_change"],"pe_oi_change":st["pe_oi_change"]})
    out={"per_strike":rows,"bias":round(agg/weight,4) if weight else 0.0,"counts":counts};ctx.put("oi",out);return PartResult(6,"Option OI Engine",output={"bias":out["bias"],"counts":counts})
