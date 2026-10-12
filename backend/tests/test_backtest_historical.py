from datetime import datetime, timedelta, timezone

from backend.backtest.historical import normalize_candles, run_ema_atr_backtest


def _candles(count=180):
    rows = []
    price = 22000.0
    for i in range(count):
        # deterministic alternating drift gives the EMA baseline crossovers.
        price += 7.0 if (i // 12) % 2 == 0 else -5.0
        stamp = (datetime(2026, 1, 1, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))) + timedelta(minutes=i)).isoformat()
        rows.append([stamp, price - 1, price + 4, price - 4, price, 1000 + i])
    return rows


def test_historical_backtest_returns_real_trade_metrics_and_discloses_proxy():
    result = run_ema_atr_backtest(
        _candles(),
        fast_period=3,
        slow_period=8,
        atr_period=5,
        stop_atr=1.2,
        target_r=1.5,
        slippage_r=0.01,
        transaction_cost_r=0.01,
    )
    assert result["ok"] is True
    assert result["mode"] == "INDEX_SPOT_PROXY"
    assert result["candle_count"] == 180
    assert result["metrics"]["n"] > 0
    assert all("gross_r" in t and "r" in t and "exit_reason" in t for t in result["trades"])
    assert any("not option-premium P&L" in item for item in result["assumptions"])


def test_historical_backtest_never_fabricates_results_for_short_history():
    result = run_ema_atr_backtest(_candles(5), fast_period=3, slow_period=8, atr_period=5)
    assert result["ok"] is False
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["trades"] == []


def test_historical_candles_are_validated_and_deduplicated():
    rows = _candles(20)
    rows.extend([rows[0], ["bad timestamp", 1, 2, 0, 1, 5], ["2026-01-01T10:00:00+05:30", -1, 2, 0, 1, 5]])
    normalized = normalize_candles(rows)
    assert len(normalized) == 20
    assert all(c["low"] <= c["open"] <= c["high"] for c in normalized)
