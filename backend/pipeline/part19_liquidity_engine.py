from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(19)
def run(ctx):
    f=ctx.get("frame") or [];atm=ctx.get("atm_strike");sp=[]
    for x in f:
        for side in ("ce","pe"):
            b=x.get(side+"_bid");a=x.get(side+"_ask")
            if b is not None and a is not None and a>=b:sp.append(a-b)
    row=next((x for x in f if x["strike"]==atm),None);ask=row.get("ce_ask") if row else None;bid=row.get("ce_bid") if row else None;ltp=row.get("ce_ltp") if row else None;atmsp=ask-bid if ask is not None and bid is not None else None;vol=sum((x.get("ce_volume") or 0)+(x.get("pe_volume") or 0) for x in f);score=max(0,1-(atmsp/max(ltp,.05))*5) if atmsp is not None and ltp else 0
    out={"avg_spread":sum(sp)/len(sp) if sp else None,"atm_spread":atmsp,"total_volume":vol,"liquidity_score":round(score,4),"wide_spread":bool(atmsp is not None and ltp and atmsp>.05*ltp),"low_liquidity":vol<1000};ctx.put("liquidity",out);return PartResult(19,"Liquidity Engine",output=out)
