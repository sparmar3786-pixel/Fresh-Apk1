import statistics
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
from backend.quant.option_math import realized_vol,returns_from_prices
@register(14)
def run(ctx):
    rows=ctx.get("frame") or [x.__dict__ for x in ctx.normalize_strikes()];atm=ctx.get("atm_strike");r=next((x for x in rows if x["strike"]==atm),None);ce=[x["ce_iv"] for x in rows if x.get("ce_iv")];pe=[x["pe_iv"] for x in rows if x.get("pe_iv")];a=statistics.mean(ce) if ce else None;b=statistics.mean(pe) if pe else None;rv=realized_vol(returns_from_prices(ctx.price_history),20)
    o={"atm":atm,"atm_ce_delta":r.get("ce_delta") if r else None,"atm_pe_delta":r.get("pe_delta") if r else None,"atm_ce_gamma":r.get("ce_gamma") if r else None,"atm_theta":r.get("ce_theta") if r else None,"avg_ce_iv":a,"avg_pe_iv":b,"iv_skew_pe_minus_ce":b-a if a is not None and b is not None else None,"realized_vol_ann":rv,"iv_minus_rv":a-rv if a is not None and rv is not None else None,"gamma_expansion":bool(r and r.get("ce_gamma") and r["ce_gamma"]>.0008)};ctx.put("greeks",o);gap=r is None or r.get("ce_delta") is None;return PartResult(14,"Greeks Engine",data_gap=gap,output=o,notes=["no greeks on ATM row"] if gap else [])
