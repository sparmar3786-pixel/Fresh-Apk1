from pathlib import Path

from backend.memory.strategy_memory import StrategyMemory


def test_strategy_memory_persists_observation_and_trade(tmp_path: Path) -> None:
    memory = StrategyMemory(str(tmp_path / "memory.sqlite"))

    memory.record_observation({
        "index": "NIFTY",
        "regime": "TRENDING",
        "strategy": "EMA_MOMENTUM",
        "strike": 25000,
        "side": "CE",
        "entry": 120,
        "oi": 100000,
        "premium": 120,
        "volume": 50000,
        "iv": 0.18,
        "greeks": {"delta": 0.52},
        "expiry": "2026-10-15",
        "time": "10:30",
        "confidence": 0.81,
    })
    memory.record_trade({
        "strategy_id": "EMA_MOMENTUM",
        "index": "NIFTY",
        "side": "CE",
        "strike": 25000,
        "entry": 120,
        "exit": 132,
        "r": 1.2,
        "result": "WIN",
        "regime": "TRENDING",
        "expiry": "2026-10-15",
        "strike_distance": 0,
        "time": "10:45",
        "is_expiry": False,
    })

    assert memory.strategy_summary("NIFTY") == {
        "n": 1,
        "win_rate": 1.0,
        "average_r": 1.2,
        "note": "sample statistic — not a forward promise",
    }
    assert memory.regime_behaviour("TRENDING", "NIFTY")["observations"] == 1
    assert memory.failure_patterns() == []
    trades = memory.trades_for_backtest("NIFTY")
    assert len(trades) == 1
    assert trades[0]["is_expiry"] is False


def test_strategy_memory_reports_failures_by_strategy_regime(tmp_path: Path) -> None:
    memory = StrategyMemory(str(tmp_path / "memory.sqlite"))
    for strategy, regime, r in [
        ("A", "RANGE", -1.0),
        ("A", "RANGE", -0.5),
        ("B", "TREND", -1.0),
    ]:
        memory.record_trade({
            "strategy_id": strategy,
            "index": "NIFTY",
            "r": r,
            "result": "LOSS",
            "regime": regime,
        })

    failures = memory.failure_patterns()
    assert failures[0]["strategy"] == "A"
    assert failures[0]["regime"] == "RANGE"
    assert failures[0]["losses"] == 2


def test_strategy_memory_handles_non_json_greeks_and_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    first = StrategyMemory(str(db))
    first.record_observation({"index": "BANKNIFTY", "greeks": object()})

    second = StrategyMemory(str(db))
    assert second.regime_behaviour(None, "BANKNIFTY")["observations"] == 1

    rows = second.trades_for_backtest()
    assert rows == []
