import pytest
from backend.backtest.engine import Backtester, compute_metrics

def test_empty_is_honest():
    assert compute_metrics([])["n"] == 0
    assert compute_metrics([])["win_rate"] is None

def test_metrics_and_views():
    trades=[{"strategy_id":"A","index":"NIFTY","side":"CE","r":1,"time":"10:15","is_expiry":False,"strike_distance":0,"regime":"TREND"},{"strategy_id":"A","index":"NIFTY","side":"PE","r":-0.5,"time":"11:20","is_expiry":True,"strike_distance":3,"regime":"RANGE"}]
    b=Backtester(trades)
    m=b.overall(); assert m["n"]==2 and m["win_rate"]==.5 and m["max_consecutive_wins"]==1
    assert set(b.ce_vs_pe())=={"CE","PE"}
    assert set(b.expiry_vs_non_expiry())=={"expiry","non_expiry"}
    assert b.out_of_sample(.5)["out_of_sample"]["n"]==1

def test_walk_forward_and_monte_carlo_are_deterministic():
    trades=[{"r":1,"strategy_id":"A"},{"r":-0.5,"strategy_id":"A"}]*3
    b=Backtester(trades)
    assert len(b.walk_forward(3))==3
    assert b.monte_carlo(50,42)==b.monte_carlo(50,42)

def test_advanced_count():
    from backend.strategies.advanced_modules import ADVANCED_COUNT, build_advanced
    assert ADVANCED_COUNT == 25
    assert len(build_advanced()) == 25


def test_advanced_module_is_data_gap_safe_and_evaluates_real_snapshot_fields():
    from backend.strategies.advanced_modules import build_advanced
    modules = build_advanced()
    assert len(modules) == 25
    result = modules[0].evaluate({"vol_surface": {"iv_slope": 0.01}})
    assert result["strategy_id"] == "X378"
    assert result["data_gap"] is False
    assert result["fired"] is True


def test_advanced_module_missing_input_never_invents_signal():
    from backend.strategies.advanced_modules import build_advanced
    result = build_advanced()[0].evaluate({})
    assert result["strategy_id"] == "X378"
    assert result["data_gap"] is True
    assert result["fired"] is False


def test_cost_adjusted_expectancy_uses_explicit_per_trade_costs():
    b = Backtester([{"r": 1.0, "slippage_r": 0.1, "transaction_cost_r": 0.2},
                    {"r": -0.2, "slippage_r": 0.0, "transaction_cost_r": 0.1}])
    report = b.cost_adjusted()
    assert report["gross"]["expectancy"] == .4
    assert report["net"]["expectancy"] == pytest.approx(.2)
