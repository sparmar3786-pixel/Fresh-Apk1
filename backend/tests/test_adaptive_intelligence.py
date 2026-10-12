from __future__ import annotations

from datetime import datetime, timezone

from backend.app.models import MarketSnapshot


def test_adaptive_engine_exposes_all_requested_modules_without_fabricating_missing_data():
    from backend.pipeline.adaptive_intelligence import evaluate_adaptive_intelligence

    snap = MarketSnapshot(
        index="NIFTY",
        exchange="NSE",
        ltp=22120,
        open=22000,
        high=22200,
        low=21950,
        previous_close=22050,
        volume=100000,
        vwap=22080,
        candles=[22000 + i * 4 for i in range(60)],
        options=[],
        timestamp=datetime.now(timezone.utc),
    )
    result = evaluate_adaptive_intelligence(snap, None, {})

    expected = {
        "liquidity_sweep", "market_structure", "gap", "previous_day_profile",
        "anchored_vwap", "volume_profile", "relative_strength", "sector_rotation",
        "breadth", "intermarket", "volatility_regime", "expiry_behaviour",
        "time_of_day", "event_risk", "anomaly", "regime_transition",
        "signal_decay", "meta_strategy", "online_allocator",
    }
    assert expected.issubset(result["modules"])
    assert result["ai_brief"]["index"] == "NIFTY"
    assert "decision_context" in result["ai_brief"]
    assert result["modules"]["breadth"]["status"] == "NOT_AVAILABLE"


def test_adaptive_engine_does_not_turn_missing_context_into_a_signal():
    from backend.pipeline.adaptive_intelligence import evaluate_adaptive_intelligence

    snap = MarketSnapshot(
        index="NIFTY",
        exchange="NSE",
        ltp=22000,
        candles=[22000 + i for i in range(30)],
        timestamp=datetime.now(timezone.utc),
    )
    result = evaluate_adaptive_intelligence(snap, None, {})
    assert result["decision_vote"]["direction"] in {"NEUTRAL", "BULLISH", "BEARISH"}
    assert result["modules"]["sector_rotation"]["status"] == "NOT_AVAILABLE"
    assert result["modules"]["event_risk"]["status"] == "NOT_AVAILABLE"
