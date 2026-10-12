from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from backend.app.models import MarketSnapshot
from .base import PartResult
from .context import PipelineContext, PipelineSettings
from . import part01_data_input, part02_data_quality, part03_market_regime, part04_price_action, part05_indicators, part06_oi_engine, part07_premium_volume, part08_seller_pressure, part09_ce_engine, part10_pe_engine, part11_opposite_side_override, part12_strike_engine, part13_support_resistance, part14_greeks_engine, part15_vol_surface, part16_order_flow, part17_multi_leg, part18_expiry_engine, part19_liquidity_engine, part20_trap_engine, part21_cross_index, part22_time_engine, part23_quant_engine, part24_entry_engine

@dataclass
class PipelineRun:
    context: PipelineContext
    parts: list[PartResult] = field(default_factory=list)
    @property
    def ok(self) -> bool: return all(p.ok for p in self.parts[:2]) and bool(self.parts)
    @property
    def flags(self) -> list[str]: return self.context.flags
    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "flags": self.flags, "parts": [p.__dict__ for p in self.parts]}

def run_pipeline(snapshot: MarketSnapshot, prev_snapshot: MarketSnapshot | None = None, ticks: list[Any] | None = None, settings: PipelineSettings | None = None, advanced: bool = True, cross_index: dict[str, float] | None = None) -> PipelineRun:
    ctx = PipelineContext(snapshot=snapshot, prev_snapshot=prev_snapshot, ticks=ticks or [], settings=settings or PipelineSettings(), advanced=advanced, index=snapshot.index)
    ctx.price_history = list(snapshot.candles)
    if cross_index is not None: ctx.put("cross_index", cross_index)
    # Always run all eight parts so missing-data evidence remains inspectable; Part 2 is the locked gate.
    funcs = [part01_data_input.run, part02_data_quality.run, part03_market_regime.run, part04_price_action.run, part05_indicators.run, part06_oi_engine.run, part07_premium_volume.run, part08_seller_pressure.run, part09_ce_engine.run, part10_pe_engine.run, part11_opposite_side_override.run, part12_strike_engine.run, part13_support_resistance.run, part14_greeks_engine.run, part15_vol_surface.run, part16_order_flow.run, part17_multi_leg.run, part18_expiry_engine.run, part19_liquidity_engine.run, part20_trap_engine.run, part21_cross_index.run, part22_time_engine.run, part23_quant_engine.run, part24_entry_engine.run]
    out = PipelineRun(ctx)
    for fn in funcs: out.parts.append(fn(ctx))
    return out
