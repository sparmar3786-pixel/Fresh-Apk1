from backend.backtest.validation import evaluate_readiness, net_of_costs, walk_forward_report


def test_costs_reduce_each_trade_and_negative_costs_are_rejected():
    rows = net_of_costs([{"r": 0.5}], slippage_r=0.1, transaction_cost_r=0.05)
    assert rows[0]["gross_r"] == 0.5
    assert abs(rows[0]["r"] - 0.35) < 1e-9
    try:
        net_of_costs([{"r": 1}], slippage_r=-0.1)
        assert False, "negative slippage must be rejected"
    except ValueError:
        pass


def test_readiness_requires_sample_win_rate_and_positive_net_expectancy():
    not_ready = evaluate_readiness([{"r": 1}] * 10)
    assert not_ready["passed"] is False
    assert not_ready["live_execution_allowed"] is False
    ready = evaluate_readiness([{"r": 1, "timestamp": f"2026-01-{i:02d}T10:00:00+00:00", "regime": "TREND"} for i in range(1, 101)],
                               slippage_r=0, transaction_cost_r=0)
    assert ready["passed"] is True
    assert ready["checks"]["minimum_trade_count"]["passed"] is True


def test_walk_forward_reports_net_regime_metrics_and_missing_timestamps():
    rows = [
        {"r": 1.0, "regime": "TREND", "timestamp": f"2026-01-{i:02d}T10:00:00+00:00"}
        for i in range(1, 11)
    ]
    report = walk_forward_report(rows, folds=5, slippage_r=0.1, transaction_cost_r=0.1)
    assert len(report["walk_forward"]) == 5
    assert report["net_metrics"]["expectancy"] < report["gross_metrics"]["expectancy"]
    assert "TREND" in report["regime_wise_net"]
    assert report["chronological"] is True
