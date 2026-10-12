from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
from backend.quant.option_math import atr,bollinger,ema,macd,rsi,vwap
@register(5)
def run(ctx):
    p=ctx.price_history;vol=[1.0]*len(p);h=[x*1.002 for x in p];l=[x*.998 for x in p];m=macd(p);b=bollinger(p,20,2.0);a=atr(h,l,p,14);spot=ctx.get("spot") or (p[-1] if p else None)
    ind={"ema8":ema(p,8),"ema13":ema(p,13),"ema20":ema(p,20),"ema50":ema(p,50),"vwap":vwap(p,vol),"rsi":rsi(p,14),"macd":m,"atr":a,"boll":b,"atr_pct":(a/spot*100) if a and spot else None};ctx.put("indicators",ind);ctx.put("atr_pct",ind["atr_pct"])
    return PartResult(5,"Indicators",output=ind)
