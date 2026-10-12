from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
def _step(strikes):
    ks=sorted(strikes);d=[b-a for a,b in zip(ks,ks[1:]) if b>a];return min(d) if d else 50.0
@register(12)
def run(ctx):
    frame=ctx.get("frame") or [];spot=ctx.get("spot") or ctx.snapshot.ltp;atm=ctx.get("atm_strike");step=_step([x["strike"] for x in frame])
    if atm is None and spot:atm=round(spot/step)*step
    band=lambda n:[atm+i*step for i in range(-n,n+1)] if atm is not None else []
    ce={x["strike"]:x["ce_oi"] or 0 for x in frame};pe={x["strike"]:x["pe_oi"] or 0 for x in frame};cco={x["strike"]:x["ce_oi_change"] or 0 for x in frame};pco={x["strike"]:x["pe_oi_change"] or 0 for x in frame}
    out={"atm":atm,"step":step,"atm_pm_3":band(3),"atm_pm_5":band(5),"max_ce_oi_strike":max(ce,key=ce.get) if ce else None,"max_pe_oi_strike":max(pe,key=pe.get) if pe else None,"max_ce_change_oi":max(cco,key=cco.get) if cco else None,"max_pe_change_oi":max(pco,key=pco.get) if pco else None,"moneyness":"ATM" if spot and atm and abs(spot-atm)<=step/2 else ("ITM" if spot and atm and spot>atm else "OTM")}
    ctx.put("strike_engine",out);return PartResult(12,"Strike Engine",output={k:v for k,v in out.items() if k not in ("atm_pm_3","atm_pm_5")})
