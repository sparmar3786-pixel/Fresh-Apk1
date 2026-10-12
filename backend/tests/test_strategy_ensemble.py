from types import SimpleNamespace

from backend.app.strategy_ensemble import evaluate_confluence


def test_confluence_reports_bullish_alignment_without_claiming_win_probability():
    snapshot = SimpleNamespace(
        timeframes={
            "1m": [{"close": 100}, {"close": 101}, {"close": 102}],
            "5m": [{"close": 98}, {"close": 99}, {"close": 101}],
        },
        options=[SimpleNamespace(side="CE", oi_change=10), SimpleNamespace(side="PE", oi_change=2)],
    )
    option = SimpleNamespace(bid=99.9, ask=100.1, ltp=100.0)
    result = evaluate_confluence(snapshot, "CALL BUY", {
        "ema_fast": 102, "ema_slow": 100, "macd_hist": 0.5, "rsi14": 60,
    }, option)
    assert result["checks"]["multi_timeframe"] == "ALIGNED"
    assert result["confluence_score"] is not None
    assert "not a probability" in result["score_meaning"]


def test_confluence_exposes_multi_timeframe_conflict():
    snapshot = SimpleNamespace(
        timeframes={
            "1m": [{"close": 100}, {"close": 101}, {"close": 102}],
            "15m": [{"close": 102}, {"close": 101}, {"close": 100}],
        },
        options=[],
    )
    result = evaluate_confluence(snapshot, "CALL BUY", {
        "ema_fast": 102, "ema_slow": 100, "macd_hist": 0.5, "rsi14": 60,
    })
    assert result["checks"]["multi_timeframe"] == "CONFLICT"
    assert result["timeframes"]["15m"] == "BEARISH"


def test_confluence_missing_data_is_unknown_not_fabricated():
    result = evaluate_confluence(SimpleNamespace(timeframes={}, options=[]), "WAIT", {})
    assert result["confluence_score"] is None
    assert result["checks"]["ema_trend"] == "UNKNOWN"
