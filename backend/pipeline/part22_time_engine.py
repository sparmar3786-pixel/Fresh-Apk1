from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from backend.pipeline.base import PartResult,register
from backend.pipeline.context import PipelineContext
@register(22)
def run(ctx):
    n=datetime.now(ZoneInfo("Asia/Kolkata"));m=n.hour*60+n.minute;op=555;cl=930;phase="pre"
    if op<=m<585:phase="opening_range"
    elif m<720:phase="morning"
    elif m<840:phase="afternoon"
    elif m<=cl:phase="last_hour"
    out={"ist_time":n.strftime("%H:%M:%S"),"phase":phase,"last_hour":phase=="last_hour","market_open":op<=m<=cl and n.weekday()<5};ctx.put("time",out);return PartResult(22,"Time Engine",output=out)
