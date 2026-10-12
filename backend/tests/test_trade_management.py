import pytest

from backend.pipeline.trade_management import build_option_levels, size_in_lots, strike_quality


def test_option_levels_use_ask_and_create_two_targets():
    plan = build_option_levels(ltp=100, bid=99, ask=100, stop_pct=0.10, min_rr=2.0)
    assert plan["ok"] is True
    assert plan["entry"] == 100
    assert plan["entry_basis"] == "best_ask"
    assert plan["execution_ready"] is True
    assert plan["stop_loss"] == 90
    assert plan["target1"] == 120
    assert plan["target2"] >= plan["target1"]


def test_missing_quote_is_reference_only_and_not_execution_ready():
    plan = build_option_levels(ltp=100, bid=None, ask=None)
    assert plan["ok"] is True
    assert plan["entry_basis"] == "ltp_reference"
    assert plan["execution_ready"] is False


def test_invalid_or_wide_quotes_fail_closed():
    assert build_option_levels(ltp=100, bid=102, ask=101)["reason"] == "crossed_quote"
    assert build_option_levels(ltp=100, bid=90, ask=100)["reason"] == "wide_spread"
    assert build_option_levels(ltp=0, bid=None, ask=None)["ok"] is False


def test_strike_quality_prefers_delta_near_half_and_tighter_spread():
    better, _ = strike_quality(
        {"strike": 22000, "ce_ltp": 100, "ce_delta": 0.5, "ce_bid": 99, "ce_ask": 100, "ce_volume": 5000},
        "CE", 22000, 50,
    )
    worse, _ = strike_quality(
        {"strike": 22100, "ce_ltp": 100, "ce_delta": 0.15, "ce_bid": 90, "ce_ask": 100, "ce_volume": 10},
        "CE", 22000, 50,
    )
    assert better < worse


def test_sizing_never_assumes_capital_or_stale_lot_sizes():
    assert size_in_lots(capital_inr=None, risk_fraction=0.01, entry=100, stop_loss=90, lot_size=25)["status"] == "capital_not_configured"
    assert size_in_lots(capital_inr=100000, risk_fraction=0.01, entry=100, stop_loss=90, lot_size=None)["status"] == "verified_lot_size_missing"
    sized = size_in_lots(capital_inr=100000, risk_fraction=0.01, entry=100, stop_loss=90, lot_size=25)
    assert sized["quantity"] == 100
    assert sized["lots"] == 4
    assert sized["estimated_max_loss_inr"] == 1000
