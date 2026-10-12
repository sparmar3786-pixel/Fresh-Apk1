from __future__ import annotations
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(11)
def run(ctx):
    ce=(ctx.get("ce_engine") or {}).get("score",0.0);pe=(ctx.get("pe_engine") or {}).get("score",0.0);net=ce+pe;action="NONE";reason=""
    if ce>2 and pe<-2 or ce<-2 and pe>2: action="BLOCK";reason="strong opposing CE/PE evidence -> block"
    elif abs(net)<.5 and (abs(ce)>1.5 or abs(pe)>1.5): action="REVERSAL-WATCH";reason="strong opposing evidence with neutral net bias"
    if action=="BLOCK" and abs(net)>3: action="EXIT";reason="strong one-sided evidence against prevailing position -> exit"
    out={"action":action,"reason":reason,"ce_score":ce,"pe_score":pe,"net":net};ctx.put("override",out);return PartResult(11,"Opposite-Side Override",output=out)
