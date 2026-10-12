from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(16)
def run(ctx):
    if not ctx.advanced:return PartResult(16,"Order Flow Engine",skipped=True,notes=["advanced engine disabled"])
    ticks=[t for t in ctx.ticks if getattr(t,"volume",None) is not None]
    if len(ticks)<3:ctx.put("order_flow",{"data_gap":True,"capability":{"trade_level":False}});return PartResult(16,"Order Flow Engine",data_gap=True,notes=["too few ticks for order-flow inference"])
    buy=sell=large=small=up=down=0;last=ticks[0].ltp
    for t in ticks[1:]:
        v=t.volume or 0
        if t.ltp>last:buy+=v;up+=1
        elif t.ltp<last:sell+=v;down+=1
        last=t.ltp;large+=v if v>=5000 else 0;small+=v if v<5000 else 0
    total=buy+sell;imb=(buy-sell)/total if total else 0;p=(up-down)/max(1,up+down);g=ctx.get("greeks") or {};out={"buy_volume":buy,"sell_volume":sell,"aggressor_volume":total,"flow_imbalance":round(imb,4),"persistence":round(p,4),"large_lot_volume":large,"small_lot_volume":small,"delta_weighted_flow":round(imb*(g.get("atm_ce_delta") or .5),4),"vega_weighted_flow":round(imb*(g.get("avg_ce_iv") or .1),5),"vega_flow_acceleration":None,"vega_flow_reversal":None,"trade_size_buckets":{"<5k":small,">=5k":large},"capability":{"trade_level":False,"method":"tick_rule_approximation"},"tick_reversal":up>0 and down>0 and abs(p)<.2};ctx.put("order_flow",out);return PartResult(16,"Order Flow Engine",output=out)
