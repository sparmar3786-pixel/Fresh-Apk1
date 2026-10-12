from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(21)
def run(ctx):
    if not ctx.advanced:return PartResult(21,"Cross-Index Engine",skipped=True,notes=["advanced engine disabled"])
    cross=ctx.get("cross_index") or {}
    if len(cross)<2:ctx.put("cross_index_res",{"data_gap":True});return PartResult(21,"Cross-Index Engine",data_gap=True,notes=["need >=2 indices for relative analysis"])
    my=cross.get(ctx.index,0);others=[v for k,v in cross.items() if k!=ctx.index];avg=sum(others)/len(others);out={"self_bias":my,"others_avg":avg,"relative_strength":round(my-avg,4),"divergence":(my>.2 and avg<-.2) or (my<-.2 and avg>.2),"leadership":max(cross,key=lambda k:abs(cross[k]))};ctx.put("cross_index_res",out);return PartResult(21,"Cross-Index Engine",output=out)
