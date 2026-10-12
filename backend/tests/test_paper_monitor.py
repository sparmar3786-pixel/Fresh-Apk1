from datetime import datetime, timezone

import pytest

from backend.backtest.paper_monitor import PaperTradeMonitor


def test_paper_monitor_net_r_and_regime_report():
    monitor = PaperTradeMonitor(max_daily_loss_r=5, max_consecutive_losses=4)
    monitor.open_trade("t1", "ORB", "NIFTY", "CE", "TREND",
                       slippage_r=0.1, transaction_cost_r=0.05)
    closed = monitor.close_trade("t1", 1.0)
    assert closed["net_r"] == pytest.approx(0.85)
    report = monitor.report()
    assert report["mode"] == "PAPER_ONLY"
    assert report["net_metrics"]["expectancy"] == pytest.approx(0.85)
    assert report["regime_wise"]["TREND"]["n"] == 1


def test_paper_monitor_blocks_duplicate_and_closed_trade():
    monitor = PaperTradeMonitor()
    monitor.open_trade("t1", "ORB", "NIFTY", "CE", "TREND")
    with pytest.raises(ValueError):
        monitor.open_trade("t1", "ORB", "NIFTY", "CE", "TREND")
    monitor.close_trade("t1", -0.5)
    with pytest.raises(ValueError):
        monitor.close_trade("t1", 1.0)


def test_paper_monitor_daily_loss_kill_switch_blocks_new_trade():
    monitor = PaperTradeMonitor(max_daily_loss_r=1.0, max_consecutive_losses=5)
    monitor.open_trade("t1", "ORB", "NIFTY", "CE", "TREND")
    monitor.close_trade("t1", -1.0)
    assert monitor.kill_switch()["blocked"] is True
    with pytest.raises(RuntimeError):
        monitor.open_trade("t2", "ORB", "NIFTY", "CE", "TREND")


def test_paper_monitor_open_trade_limit():
    monitor = PaperTradeMonitor(max_open_trades=1)
    monitor.open_trade("t1", "ORB", "NIFTY", "CE", "TREND")
    with pytest.raises(RuntimeError):
        monitor.open_trade("t2", "VWAP", "BANKNIFTY", "PE", "RANGE")



def test_paper_monitor_persists_across_instances(tmp_path):
    path = str(tmp_path / "paper.sqlite3")
    first = PaperTradeMonitor(storage_path=path)
    first.open_trade("durable-1", "ORB", "NIFTY", "CE", "TREND", slippage_r=0.1)
    first.close_trade("durable-1", 1.0)
    restarted = PaperTradeMonitor(storage_path=path)
    report = restarted.report()
    assert report["closed_trades"] == 1
    assert report["net_metrics"]["expectancy"] == pytest.approx(0.9)
    assert report["persistence"] == "sqlite"
