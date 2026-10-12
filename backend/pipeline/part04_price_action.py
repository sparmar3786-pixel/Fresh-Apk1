from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
def _swings(prices,look=2):
    highs=[];lows=[]
    for i in range(look,len(prices)-look):
        w=prices[i-look:i+look+1]
        if prices[i]==max(w):highs.append(prices[i])
        if prices[i]==min(w):lows.append(prices[i])
    return highs,lows
@register(4)
def run(ctx):
    prices=ctx.price_history;out={"hh_hl":False,"lh_ll":False,"bos":False,"choch":False,"last_high":None,"last_low":None}
    if len(prices)>=10:
        highs,lows=_swings(prices)
        if len(highs)>=2 and len(lows)>=2:out.update(hh_hl=highs[-1]>highs[-2] and lows[-1]>lows[-2],lh_ll=highs[-1]<highs[-2] and lows[-1]<lows[-2],last_high=highs[-1],last_low=lows[-1])
        spot=prices[-1]
        if highs and spot>highs[-1]:out["bos"]=True
        if lows and spot<lows[-1]:out["choch"]=True
    ctx.put("price_action",out);return PartResult(4,"Price Action",output=out)
