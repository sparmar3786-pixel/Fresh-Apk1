from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
STRUCTURES=["Long Call","Long Put","Short Call","Short Put","Bull Call Spread","Bear Call Spread","Bull Put Spread","Bear Put Spread","Long Straddle","Short Straddle","Long Strangle","Short Strangle","Calendar Spread","Butterfly","Iron Butterfly","Condor","Iron Condor","Ratio Spread","Collar","Covered Call","Covered Put","Strip","Strap"]
def _step(k):
 d=[b-a for a,b in zip(sorted(k),sorted(k)[1:]) if b>a];return min(d) if d else 50
@register(17)
def run(ctx):
 if not ctx.advanced:return PartResult(17,"Multi-Leg Options",skipped=True,notes=["advanced engine disabled"])
 rows=ctx.get("frame") or [x.__dict__ for x in ctx.normalize_strikes()];a=ctx.get("atm_strike")
 if a is None:return PartResult(17,"Multi-Leg Options",data_gap=True,notes=["ATM strike unavailable"])
 st=_step([x["strike"] for x in rows]);h={x["strike"]:x.get("ce_ltp") is not None and x.get("pe_ltp") is not None for x in rows};base=h.get(a,False);up=h.get(a+st,False);dn=h.get(a-st,False);b=[]
 if base:b+=["Long Call","Long Put","Short Call","Short Put","Long Straddle","Short Straddle","Covered Call","Covered Put"]
 if base and up:b+=["Bull Call Spread","Bull Put Spread","Long Strangle","Short Strangle","Collar","Ratio Spread"]
 if base and dn:b+=["Bear Call Spread","Bear Put Spread","Strip","Strap"]
 if base and up and dn:b+=["Butterfly","Iron Butterfly","Condor","Iron Condor"]
 o={"structures_recognized":sorted(set(b)),"structures_total":len(STRUCTURES),"missing_leg_gap":sorted(set(STRUCTURES)-set(b))};ctx.put("multi_leg",o);return PartResult(17,"Multi-Leg Options",output={"recognized":len(o["structures_recognized"]),"total":len(STRUCTURES)})
