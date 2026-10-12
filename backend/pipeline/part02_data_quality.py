from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime,timezone
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@dataclass
class QualityReport:
    passed:bool=True; flags:list[str]=field(default_factory=list); reasons:list[str]=field(default_factory=list); age_sec:float=0.0
    def fail(self,flag,reason): self.passed=False;self.flags.append(flag);self.reasons.append(reason)
def evaluate_quality(ctx):
    r=QualityReport();now=datetime.now(timezone.utc);ts=ctx.snapshot.timestamp
    if ts.tzinfo is None:ts=ts.replace(tzinfo=timezone.utc)
    r.age_sec=(now-ts).total_seconds()
    if r.age_sec>ctx.settings.max_snapshot_age_sec:r.fail("STALE",f"snapshot age {r.age_sec:.1f}s > {ctx.settings.max_snapshot_age_sec}s")
    f=ctx.get("frame") or []
    if not f:r.fail("GAP","empty option chain")
    seen=set();moi=mvol=0
    for s in f:
        k=s["strike"]
        if k<=0 or k in seen:r.fail("INVALID_STRIKE",f"invalid/dup strike {k}")
        seen.add(k);moi+=s["ce_oi"] is None or s["pe_oi"] is None;mvol+=s["ce_volume"] is None or s["pe_volume"] is None
    if f and moi>len(f)*.5:r.fail("MISSING_OI",f"{moi}/{len(f)} strikes missing OI")
    if f and mvol>len(f)*.5:r.fail("MISSING_VOLUME",f"{mvol}/{len(f)} strikes missing volume")
    return r
@register(2)
def run(ctx):
    r=evaluate_quality(ctx);ctx.put("dq",r)
    if not r.passed:ctx.flag("DATA_QUALITY_FAIL")
    return PartResult(2,"Data Quality Engine",r.passed,not r.passed,{"passed":r.passed,"flags":r.flags,"reasons":r.reasons,"age":r.age_sec})
