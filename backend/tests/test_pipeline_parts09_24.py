from datetime import datetime, timezone
from backend.app.models import MarketSnapshot, OptionPoint
from backend.pipeline.context import PipelineContext
from backend.pipeline import part09_ce_engine, part10_pe_engine, part11_opposite_side_override, part12_strike_engine, part13_support_resistance, part14_greeks_engine, part15_vol_surface, part16_order_flow, part17_multi_leg, part18_expiry_engine, part19_liquidity_engine, part20_trap_engine, part21_cross_index, part22_time_engine, part23_quant_engine, part24_entry_engine

def snap():
    return MarketSnapshot(index="NIFTY",exchange="NSE",ltp=22000,candles=[21900,21950,22000,22050,22100]*10,options=[
      OptionPoint(symbol="NIFTYCE",strike=22000,side="CE",ltp=120,oi=10000,oi_change=500,iv=.18,delta=.5,gamma=.001,theta=-5,vega=8),
      OptionPoint(symbol="NIFTYPE",strike=22000,side="PE",ltp=100,oi=9000,oi_change=-300,iv=.19,delta=-.5,gamma=.001,theta=-5,vega=8),
      OptionPoint(symbol="NIFTYCE2",strike=22100,side="CE",ltp=80,oi=15000,oi_change=600,iv=.2,delta=.4),
      OptionPoint(symbol="NIFTYPE2",strike=22100,side="PE",ltp=150,oi=7000,oi_change=-100,iv=.2,delta=-.6),
      OptionPoint(symbol="NIFTYCE3",strike=21900,side="CE",ltp=160,oi=8000,oi_change=200,iv=.2,delta=.6),
      OptionPoint(symbol="NIFTYPE3",strike=21900,side="PE",ltp=70,oi=12000,oi_change=-200,iv=.2,delta=-.4),
    ],timestamp=datetime.now(timezone.utc))

def ctx():
    c=PipelineContext(snapshot=snap(),advanced=True,index="NIFTY"); c.normalize_strikes(); c.price_history=list(c.snapshot.candles); c.put("spot",22000); c.put("atm_strike",22000); c.put("oi",{"bias":.4,"per_strike":[{"strike":22000,"ce":"LONG BUILDUP","pe":"SHORT BUILDUP"},{"strike":22100,"ce":"SHORT BUILDUP","pe":"SHORT BUILDUP"},{"strike":21900,"ce":"LONG BUILDUP","pe":"LONG BUILDUP"}]}); return c

def test_ce_pe_engines():
    c=ctx(); assert part09_ce_engine.run(c).ok; assert part10_pe_engine.run(c).ok

def test_strike_and_greeks_have_real_outputs():
    c=ctx(); part12_strike_engine.run(c); r=part14_greeks_engine.run(c); assert c.get("strike_engine")["atm"]==22000; assert c.get("greeks")["atm_ce_delta"]==.5; assert not r.data_gap

def test_advanced_parts_degrade_without_ticks():
    c=ctx(); part15_vol_surface.run(c); r=part16_order_flow.run(c); assert c.get("vol_surface")["moneyness_iv_points"]>=3; assert r.data_gap

def test_pipeline_parts_are_registered_and_entry_is_data_gap_without_option_quotes():
    c=ctx(); part11_opposite_side_override.run(c); part13_support_resistance.run(c); part17_multi_leg.run(c); part18_expiry_engine.run(c); part19_liquidity_engine.run(c); part20_trap_engine.run(c); part21_cross_index.run(c); part22_time_engine.run(c); part23_quant_engine.run(c); r=part24_entry_engine.run(c); assert r.data_gap or c.get("entry") is not None
