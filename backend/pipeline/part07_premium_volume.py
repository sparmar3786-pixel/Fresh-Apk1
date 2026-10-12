from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
from backend.quant.option_math import safe_pct_change
@register(7)
def run(ctx):
    atm=ctx.get("atm_strike");ks=sorted(s["strike"] for s in ctx.get("frame") or []);diffs=[b-a for a,b in zip(ks,ks[1:]) if b>a];step=min(diffs) if diffs else 50;ce=pe=None;cv=pv=total=0
    for st in ctx.get("frame") or []:
        if atm is not None and abs(st["strike"]-atm)<=2*step:
            if st["ce_ltp"] is not None:ce=safe_pct_change(st["ce_ltp"],st["ce_prev_ltp"])
            if st["pe_ltp"] is not None:pe=safe_pct_change(st["pe_ltp"],st["pe_prev_ltp"])
            cv+=st["ce_volume"] or 0;pv+=st["pe_volume"] or 0;total+=st["ce_volume"] or 0;total+=st["pe_volume"] or 0
    bias=(ce-pe)/100 if ce is not None and pe is not None else 0.0;confirm=cv/total if total else .5;out={"ce_mom_pct":ce,"pe_mom_pct":pe,"bias":round(bias,4),"ce_vol_share":round(confirm,4),"total_volume":total};ctx.put("premium_volume",out);return PartResult(7,"Premium + Volume Engine",output=out)
