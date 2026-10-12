from __future__ import annotations
from backend.app.models import OISignal
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(8)
def run(ctx):
    per=(ctx.get("oi") or {}).get("per_strike") or [];pressure=0;cover=[]
    for row in per:
        if row["ce"]==OISignal.SHORT_BUILDUP.value:pressure-=1
        if row["pe"]==OISignal.SHORT_BUILDUP.value:pressure+=1
        if row["ce"]==OISignal.SHORT_COVERING.value or row["pe"]==OISignal.SHORT_COVERING.value:cover.append(row["strike"])
    out={"seller_pressure":round(pressure/max(1,len(per)),4),"probable_covering_strikes":sorted(set(cover)),"note":"probable zone inferred from observable OI/premium; not a hidden-level claim"};ctx.put("seller_pressure",out);return PartResult(8,"Seller Pressure Engine",output=out)
