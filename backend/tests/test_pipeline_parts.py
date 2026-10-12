from datetime import datetime, timezone

import pytest

from backend.app.models import MarketSnapshot, OptionPoint


def sample_snapshot():
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
        index="NIFTY", exchange="NSE", ltp=22000, candles=[22000 + i for i in range(60)], timestamp=now,
        options=[
            OptionPoint(symbol="NIFTYCE", strike=22000, side="CE", ltp=120, oi=1000, oi_change=100, premium_change=5, volume=500),
            OptionPoint(symbol="NIFTYPE", strike=22000, side="PE", ltp=100, oi=900, oi_change=-50, premium_change=-3, volume=450),
        ],
    )


def test_pipeline_parts_1_to_8_produce_normalized_evidence():
    from backend.pipeline import run_pipeline

    result = run_pipeline(sample_snapshot())
    assert result.ok
    assert result.context.get("spot") == 22000
    assert result.context.get("atm_strike") == 22000
    assert result.context.get("dq").passed is True
    assert result.context.get("regime")
    assert result.context.get("price_action")
    assert result.context.get("indicators")
    assert result.context.get("oi")["per_strike"]
    assert result.context.get("premium_volume")
    assert result.context.get("seller_pressure")


def test_pipeline_data_quality_is_a_hard_failure_for_stale_data():
    from backend.pipeline import run_pipeline

    snap = sample_snapshot()
    snap.timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
    result = run_pipeline(snap)
    assert not result.ok
    assert "DATA_QUALITY_FAIL" in result.flags
    assert any(part.part == 2 and not part.ok for part in result.parts)


def test_pipeline_does_not_invent_missing_spot_or_chain():
    from backend.pipeline import run_pipeline

    snap = sample_snapshot()
    snap.options = []
    result = run_pipeline(snap)
    assert not result.ok
    assert result.context.get("frame") == []
    assert result.context.get("spot") == 22000
    assert "DATA_QUALITY_FAIL" in result.flags
