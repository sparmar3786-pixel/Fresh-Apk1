from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(13)
def run(ctx):
    spot=ctx.get("spot") or ctx.snapshot.ltp;hi=spot;lo=spot;prev=None; st=ctx.get("strike_engine") or {}; rng=hi-lo;p=(hi+lo+(prev or spot))/3;r1=2*p-lo;s1=2*p-hi;r2=p+rng;s2=p-rng
    out={"context_only":True,"ce_resistance_oi":st.get("max_ce_oi_strike"),"pe_support_oi":st.get("max_pe_oi_strike"),"pdh":None,"pdl":None,"day_high":hi,"day_low":lo,"prev_close":prev,"weekly_ref":{"week_high":None,"week_low":None},"pivots":{"pivot":round(p,2),"r1":round(r1,2),"s1":round(s1,2),"r2":round(r2,2),"s2":round(s2,2)},"cpr":{"top":round((hi+lo)/2,2),"bottom":round((p+(prev or spot))/2,2)},"fibonacci":{}}
    ctx.put("sr",out);return PartResult(13,"Support / Resistance (context only)",output={"context_only":True,"pivots":out["pivots"]})
