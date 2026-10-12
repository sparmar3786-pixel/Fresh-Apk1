from types import SimpleNamespace

from backend.app.research_strategy_pack import evaluate_research_pack


def test_research_pack_reports_aligned_trend_and_flow():
    snapshot = SimpleNamespace(options=[
        SimpleNamespace(side="CE", oi_change=10, premium_change=2),
        SimpleNamespace(side="PE", oi_change=5, premium_change=-1),
    ])
    option = SimpleNamespace(bid=99.9, ask=100.1, ltp=100.0, volume=1200)
    result = evaluate_research_pack(
        snapshot, "CALL BUY",
        {"ema_fast": 105, "ema_slow": 100, "macd_hist": 0.5, "rsi14": 60, "zscore20": 0.4},
        option,
    )
    assert result["checks"]["trend_following"]["state"] == "BULLISH"
    assert result["checks"]["option_oi_premium_flow"]["observations"] == 2
    assert result["checks"]["execution_liquidity"]["state"] == "TIGHT"
    assert result["candidate_alignment"] == "ALIGNED"
    assert "not probability" in result["score_meaning"]


def test_research_pack_keeps_missing_inputs_unknown():
    result = evaluate_research_pack(SimpleNamespace(options=[]), "CALL BUY", {})
    assert result["checks"]["trend_following"]["state"] == "UNKNOWN"
    assert result["checks"]["mean_reversion"]["state"] == "UNKNOWN"
    assert result["checks"]["option_oi_premium_flow"]["state"] == "UNKNOWN"
    assert result["checks"]["execution_liquidity"]["state"] == "UNKNOWN"
    assert result["evidence_score"] is None


def test_research_pack_does_not_turn_mean_reversion_watch_into_order():
    result = evaluate_research_pack(
        SimpleNamespace(options=[]), "WAIT",
        {"rsi14": 25, "zscore20": -2.4},
    )
    assert result["checks"]["mean_reversion"]["state"] == "OVERSOLD_REVERSAL_WATCH"
    assert result["candidate_alignment"] == "UNKNOWN"
    assert "Diagnostics only" in result["safety_note"]
