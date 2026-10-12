from datetime import datetime, timedelta, timezone

from backend.app.models import MarketSnapshot, OptionPoint, TradeDecision
from backend.app.strategies import analyze, build_qualified_trade_plans


def snapshot(bullish: bool = True) -> MarketSnapshot:
    candles = [100 + (i * 0.8 if bullish else -i * 0.8) for i in range(40)]
    options = [
        OptionPoint(symbol="NIFTY", strike=25000, side="CE", ltp=120, volume=1000, oi=5000, oi_change=700, premium_change=0.12),
        OptionPoint(symbol="NIFTY", strike=25000, side="PE", ltp=90, volume=900, oi=3000, oi_change=-350, premium_change=-0.08),
        OptionPoint(symbol="NIFTY", strike=25100, side="CE", ltp=80, volume=800, oi=4200, oi_change=500, premium_change=0.10),
        OptionPoint(symbol="NIFTY", strike=25100, side="PE", ltp=60, volume=700, oi=3400, oi_change=-200, premium_change=-0.06),
    ]
    return MarketSnapshot(index="NIFTY", exchange="NFO", ltp=candles[-1], candles=candles, options=options, timestamp=datetime.now(timezone.utc))


def test_bullish_alignment_selects_call_candidate():
    result = analyze(snapshot(True))
    assert result.decision == TradeDecision.CALL_BUY
    assert result.option_side == "CE"
    assert result.strike is not None
    assert result.entry is not None
    assert result.target is not None


def test_no_option_chain_cannot_issue_directional_signal():
    s = snapshot(True)
    s.options = []
    result = analyze(s)
    assert result.decision == TradeDecision.NO_TRADE
    assert "OPTION_CHAIN_MISSING" in result.guards


def test_stale_data_is_no_trade():
    s = snapshot(True)
    s.timestamp = datetime.now(timezone.utc) - timedelta(seconds=30)
    result = analyze(s, stale_after_seconds=15)
    assert result.decision == TradeDecision.NO_TRADE
    assert "STALE_DATA" in result.guards


def test_trade_plan_count_is_only_the_number_that_qualifies_and_caps_at_five():
    results = []
    for i in range(6):
        result = analyze(snapshot(True))
        result.index = f"INDEX{i}"
        result.confidence = 90 - i
        results.append(result)
    plans = build_qualified_trade_plans(results, limit=5)
    assert len(plans) == 5
    assert [p["index"] for p in plans] == [f"INDEX{i}" for i in range(5)]


def test_trade_plan_excludes_guarded_signal():
    result = analyze(snapshot(True))
    result.guards.append("STALE_DATA")
    assert build_qualified_trade_plans([result], limit=5) == []


def test_advanced_ohlc_indicators_are_returned_when_history_is_available():
    rows = []
    price = 22000.0
    for i in range(220):
        price += 8.0 if (i // 10) % 2 == 0 else -3.0
        rows.append({
            "start": f"2026-01-{1 + i // 60:02d}T09:15:00+00:00",
            "open": price - 1.0,
            "high": price + 4.0,
            "low": price - 4.0,
            "close": price,
            "volume": 1000 + i,
        })
    s = snapshot(True)
    s.timeframes = {"5m": rows}
    result = analyze(s)
    indicators = result.indicators
    assert isinstance(indicators["ema50"], float)
    assert isinstance(indicators["ema200"], float)
    assert isinstance(indicators["stochastic_k14"], float)
    assert isinstance(indicators["williams_r14"], float)
    assert isinstance(indicators["roc10_pct"], float)
    assert isinstance(indicators["adx14"], float)
    assert indicators["supertrend_direction"] in {"UP", "DOWN"}
    assert indicators["support20"] <= indicators["resistance20"]
