from __future__ import annotations
from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext
from backend.quant.option_math import ema, vwap
def classify_regime(prices,spot,atr_pct):
    if not prices or spot is None or len(prices)<5: return "UNCERTAIN",0.0
    e20=ema(prices,20) or spot; e50=ema(prices,50) or spot; vw=vwap(prices,[1.0]*len(prices)) or spot; slope=(e20-e50)/e50 if e50 else 0; above=(spot-vw)/vw if vw else 0; vol=atr_pct or 0
    if vol>1.2:return "HIGH_VOL",vol
    if vol<0.25:return "LOW_VOL",vol
    if slope>0.0015 and above>0:return "STRONG_BULL",slope
    if slope<-0.0015 and above<0:return "STRONG_BEAR",slope
    if abs(slope)<0.0005:return "SIDEWAYS",slope
    return ("BREAKOUT" if above>0.002 else "MEAN_REVERSION"),slope
@register(3)
def run(ctx):
    regime,score=classify_regime(ctx.price_history,ctx.get("spot"),ctx.get("atr_pct")); ctx.put("regime",regime);ctx.put("regime_score",score);return PartResult(3,"Market Regime",output={"regime":regime,"score":round(score,6)})
