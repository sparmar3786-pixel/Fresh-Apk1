from __future__ import annotations
from datetime import datetime,timezone
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
def days_to_expiry(expiry):
    if not expiry:return None
    for fmt in ("%d%b%Y","%d-%b-%Y","%d%b%y"):
        try:return max(0,(datetime.strptime(expiry.upper(),fmt).replace(tzinfo=timezone.utc)-datetime.now(timezone.utc)).days)
        except ValueError:pass
    return None
@register(18)
def run(ctx):
    expiry=ctx.get("expiry");d=days_to_expiry(expiry);out={"expiry":expiry,"days_to_expiry":d,"is_expiry_day":d==0,"expiry_week":d is not None and d<=3,"gamma_risk_zone":d is not None and d<=1};ctx.put("expiry_info",out);return PartResult(18,"Expiry Engine",output=out)
