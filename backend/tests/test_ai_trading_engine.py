from __future__ import annotations

from datetime import datetime, timezone, timedelta

from backend.pipeline.ai_trading_engine import (
    evaluate_multi_timeframe,
    choose_strike,
    build_trade_plan,
    evaluate_exit,
)


def _series(start: float, step: float, count: int = 40) -> list[float]:
    return [start + step * i for i in range(count)]


def test_multitimeframe_requires_higher_timeframe_alignment_before_entry():
    bars = {
        "15m": _series(100, 1.0),
        "5m": _series(100, 0.5),
        "1m": _series(100, 0.25),
    }
    result = evaluate_multi_timeframe(bars, "CE")
    assert result["eligible"] is True
    assert result["regime"] == "BULLISH"
    assert result["entry_timeframe"] == "1m"
    assert result["setup_timeframe"] == "5m"
    assert result["regime_timeframe"] == "15m"
    assert result["confidence"] >= 70


def test_multitimeframe_blocks_countertrend_trigger():
    bars = {
        "15m": _series(140, 1.0),
        "5m": _series(120, 0.5),
        "1m": _series(130, -0.4),
    }
    result = evaluate_multi_timeframe(bars, "CE")
    assert result["eligible"] is False
    assert "TRIGGER_NOT_ALIGNED" in result["blocks"]


def test_strike_selection_prefers_delta_liquidity_and_tighter_spread():
    options = [
        {"symbol": "NIFTYCE1", "strike": 22000, "side": "CE", "ltp": 100, "bid": 99.8, "ask": 100.1, "delta": 0.50, "volume": 50000, "oi": 200000, "dte": 3},
        {"symbol": "NIFTYCE2", "strike": 22100, "side": "CE", "ltp": 70, "bid": 60, "ask": 75, "delta": 0.35, "volume": 90000, "oi": 250000, "dte": 3},
    ]
    chosen = choose_strike(options, "CE", 22000)
    assert chosen["symbol"] == "NIFTYCE1"
    assert chosen["selection_grade"] in {"A", "A+"}


def test_trade_plan_has_entry_stop_three_targets_and_time_exit():
    plan = build_trade_plan(
        index="NIFTY",
        side="CE",
        strike=22000,
        option={"symbol": "NIFTYCE1", "ltp": 100, "bid": 99.9, "ask": 100.1, "delta": 0.5},
        timeframe={"eligible": True, "atr": 20.0, "trigger_price": 22010.0, "invalidation_price": 21970.0, "confidence": 82},
        now=datetime.now(timezone.utc),
        minutes_to_session_close=120,
    )
    assert plan["eligible"] is True
    assert plan["entry"] == 100.1
    assert plan["stop_loss"] < plan["entry"]
    assert plan["target1"] > plan["entry"]
    assert plan["target2"] > plan["target1"]
    assert plan["target3"] > plan["target2"]
    assert plan["rr_target1"] >= 1.5
    assert plan["time_exit_minutes"] <= 45
    assert plan["advisory_only"] is True


def test_exit_engine_handles_stop_target_signal_flip_and_time_stop():
    opened = datetime.now(timezone.utc) - timedelta(minutes=40)
    common = {
        "side": "CE",
        "entry": 100.0,
        "stop_loss": 90.0,
        "target1": 115.0,
        "target2": 125.0,
        "target3": 135.0,
        "opened_at": opened.isoformat(),
        "time_exit_minutes": 30,
    }
    assert evaluate_exit({**common, "ltp": 89.0, "signal_side": "CE"})["action"] == "EXIT_STOP"
    assert evaluate_exit({**common, "ltp": 116.0, "signal_side": "CE"})["action"] == "TRAIL_AFTER_T1"
    assert evaluate_exit({**common, "ltp": 110.0, "signal_side": "PE"})["action"] == "EXIT_SIGNAL_FLIP"
    assert evaluate_exit({**common, "ltp": 102.0, "signal_side": "CE"})["action"] == "EXIT_TIME"


def test_smartapi_depth_prices_are_normalized_to_rupees():
    from backend.app.angel import AngelGateway

    bid, ask = AngelGateway._best_bid_ask({
        "best_5_buy_data": [{"price": 9990}],
        "best_5_sell_data": [{"price": 10010}],
    })
    assert bid == 99.9
    assert ask == 100.1


def test_ai_decision_cannot_reverse_deterministic_direction():
    from backend.app.ai import sanitize_ai_decision
    from backend.app.models import TradeDecision

    decision, flags = sanitize_ai_decision(TradeDecision.CALL_BUY, TradeDecision.PUT_BUY, [])
    assert decision == TradeDecision.WAIT
    assert "AI_OPPOSITE_DIRECTION_BLOCK" in flags

    decision, flags = sanitize_ai_decision(TradeDecision.CALL_BUY, TradeDecision.CALL_BUY, [])
    assert decision == TradeDecision.CALL_BUY
    assert flags == []
