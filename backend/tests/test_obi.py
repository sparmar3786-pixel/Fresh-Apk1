from __future__ import annotations

from backend.app.obi import OBIEngine, OBIParams


def tick(ltp: float, bid_qty: int = 100, ask_qty: int = 10) -> dict:
    return {
        "token": "12345",
        "symbol": "TEST",
        "last_traded_price": ltp,
        "source": "unit-test",
        "best_5_buy_data": [
            {"price": 10000, "quantity": bid_qty},
            {"price": 9995, "quantity": bid_qty // 2},
        ],
        "best_5_sell_data": [
            {"price": 10005, "quantity": ask_qty},
            {"price": 10010, "quantity": ask_qty // 2},
        ],
    }


def test_obi_waits_until_momentum_history_exists() -> None:
    engine = OBIEngine(OBIParams(momentum_ticks=2, persistence=1))
    engine.on_tick(tick(100.00))
    snap = engine.snapshot()
    assert snap["count"] == 1
    row = snap["signals"]["12345"]
    assert row["status"] == "WAIT"
    assert row["reason"] == "Collecting momentum history"


def test_obi_emits_signal_only_after_aligned_persistent_ticks() -> None:
    engine = OBIEngine(OBIParams(
        obi_threshold=0.1,
        min_micro_edge_bps=0.1,
        max_spread_bps=8.0,
        momentum_ticks=2,
        persistence=1,
        cooldown_sec=0.0,
    ))
    engine.on_tick(tick(100.00))
    engine.on_tick(tick(100.01))
    engine.on_tick(tick(100.02))
    row = engine.snapshot()["signals"]["12345"]
    assert row["status"] == "BUY"
    assert row["reference_price"] == 100.05
    assert row["source"] == "unit-test"


def test_obi_missing_depth_never_creates_trade_signal() -> None:
    engine = OBIEngine()
    engine.on_tick({"token": "12345", "last_traded_price": 100.0})
    row = engine.snapshot()["signals"]["12345"]
    assert row["status"] == "WAIT"
    assert "depth unavailable" in row["reason"]
