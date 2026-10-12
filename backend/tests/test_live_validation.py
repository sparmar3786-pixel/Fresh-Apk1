from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from backend.app.live_validation import validate_live_candidate


def _candidate(now=None, **overrides):
    now = now or datetime.now(timezone.utc)
    option = SimpleNamespace(
        side="CE",
        strike=25000.0,
        ltp=100.0,
        bid=99.9,
        ask=100.1,
        timestamp=now,
    )
    snapshot = SimpleNamespace(
        index="NIFTY",
        timestamp=now,
        source="angel-one-websocket",
        options=[option],
    )
    strategy = SimpleNamespace(
        index="NIFTY",
        decision="CALL BUY",
        confidence=82.0,
        guards=[],
        strike=25000.0,
        option_side="CE",
        entry=100.1,
        stop_loss=90.0,
        target=120.0,
    )
    ai = SimpleNamespace(
        index="NIFTY",
        decision="CALL BUY",
        confidence=80.0,
        action="CALL BUY",
        risk_flags=[],
        generated_at=now,
    )
    return strategy, snapshot, ai, overrides


def test_live_validation_passes_only_for_fresh_matching_ai_and_quote():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "PASS"
    assert result["decision"] == "CALL BUY"
    assert result["blocks"] == []


def test_live_validation_blocks_stale_snapshot():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now - timedelta(seconds=60))
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "FAIL"
    assert "STALE_MARKET_DATA" in result["blocks"]
    assert result["decision"] == "WAIT"


def test_live_validation_blocks_ai_direction_conflict():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    ai.decision = "PUT BUY"
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "FAIL"
    assert "AI_DIRECTION_MISMATCH" in result["blocks"]


def test_live_validation_blocks_missing_ai_and_risk_flags():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    assert "AI_NOT_VALIDATED" in validate_live_candidate(strategy, snapshot, None, now=now, **overrides)["blocks"]
    ai.risk_flags = ["OI_CONFLICT"]
    assert "AI_RISK_FLAGS_PRESENT" in validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)["blocks"]


def test_live_validation_blocks_bad_spread_and_wrong_option_side():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    snapshot.options[0].ask = 120.0
    assert "OPTION_SPREAD_TOO_WIDE" in validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)["blocks"]
    snapshot.options[0].ask = 100.1
    strategy.option_side = "PE"
    assert "SIGNAL_OPTION_SIDE_MISMATCH" in validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)["blocks"]


def test_live_validation_blocks_rest_fallback_and_strategy_guards():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    snapshot.source = "angel-one-rest-fallback"
    assert "WEBSOCKET_SOURCE_REQUIRED" in validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)["blocks"]
    snapshot.source = "angel-one-websocket"
    strategy.guards = ["MTF_WARMUP_INCOMPLETE"]
    assert "STRATEGY_GUARDS_PRESENT" in validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)["blocks"]



def test_put_buy_candidate_returns_validated_sell_direction():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    strategy.decision = "PUT BUY"
    strategy.option_side = "PE"
    snapshot.options[0].side = "PE"
    ai.decision = "PUT BUY"
    ai.action = "PUT BUY"
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "PASS"
    assert result["decision"] == "PUT BUY"
    assert result["market_direction"] == "SELL"



def test_live_validation_blocks_invalid_entry_stop_target_order():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    strategy.stop_loss = 101.0
    strategy.entry = 100.1
    strategy.target = 120.0
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "FAIL"
    assert "INVALID_ENTRY_SL_TARGET" in result["blocks"]
    assert result["decision"] == "WAIT"


def test_live_validation_blocks_reward_risk_below_configured_minimum():
    now = datetime.now(timezone.utc)
    strategy, snapshot, ai, overrides = _candidate(now)
    strategy.stop_loss = 90.0
    strategy.entry = 100.1
    strategy.target = 110.0
    result = validate_live_candidate(strategy, snapshot, ai, now=now, **overrides)
    assert result["verdict"] == "FAIL"
    assert "REWARD_RISK_TOO_LOW" in result["blocks"]
    assert result["decision"] == "WAIT"
