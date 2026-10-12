from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
from backend.quant.option_math import percentile_rank,realized_vol,returns_from_prices,rolling_correlation,rolling_zscore,zscore
@register(23)
def run(ctx):
    p=ctx.price_history;out={"data_gap":False}
    if len(p)<5:out["data_gap"]=True;ctx.put("quant",out);return PartResult(23,"Quant Engine",data_gap=True,output=out)
    r=returns_from_prices(p);rz=rolling_zscore(p,20);pct=percentile_rank(p[-1],p);mom=p[-1]/p[max(0,len(p)-20)]-1;vol=realized_vol(r,20) or 0;oi=(ctx.get("oi") or {}).get("bias",0);norm=lambda x,s:max(-1,min(1,x/s)) if s else 0
    out.update(zscore=zscore(p[-1],p),rolling_z=rz,percentile=pct,momentum_factor=mom,vol_adjusted_momentum=mom/vol if vol else None,mean_reversion_signal=rz is not None and abs(rz)>2,outlier=pct is not None and (pct>97 or pct<3),anomaly=rz is not None and abs(rz)>3,return_mean=float(r.mean()) if len(r) else 0,return_std=float(r.std()) if len(r) else 0,norm_momentum=norm(mom,.01),norm_volatility=norm(vol,.3),norm_oi_bias=norm(oi,.5),rolling_correlation=rolling_correlation(p,p,20));ctx.put("quant",out);return PartResult(23,"Quant Engine",output=out)
