from __future__ import annotations
import numpy as np
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(15)
def run(ctx):
    if not ctx.advanced:return PartResult(15,"Volatility Surface Engine",skipped=True,notes=["advanced engine disabled"])
    rows=ctx.get("frame") or [x.__dict__ for x in ctx.normalize_strikes()];spot=ctx.get("spot") or ctx.snapshot.ltp;pts=[(x["strike"],x["ce_iv"]) for x in rows if x.get("ce_iv") is not None]
    if spot<=0 or len(pts)<3:ctx.put("vol_surface",{"data_gap":True,"moneyness_iv_points":len(pts)});return PartResult(15,"Volatility Surface Engine",data_gap=True,notes=["insufficient IV points for surface"])
    x=np.array([(k-spot)/spot for k,_ in pts]);y=np.array([v for _,v in pts]);coef=np.polyfit(x,y,2);slope=float(np.polyfit(x,y,1)[0]);atm=float(np.interp(0,x,y));otm=float(np.mean(y[x>.01])) if (x>.01).any() else atm;o={"iv_slope":slope,"iv_curvature":float(coef[0]),"atm_iv":atm,"otm_vs_atm_iv":otm-atm,"smile":bool(coef[0]>0),"skew":slope,"surface_shift":0.0,"term_structure":{"slope":None,"inverted":None,"note":"needs multiple expiries"},"moneyness_iv_points":len(pts)};ctx.put("vol_surface",o);return PartResult(15,"Volatility Surface Engine",output=o)
