from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _decision(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().upper()


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def validate_live_candidate(
    strategy: Any,
    snapshot: Any,
    ai: Any,
    *,
    stale_after_seconds: int = 15,
    min_strategy_confidence: float = 65.0,
    min_ai_confidence: float = 65.0,
    max_spread_fraction: float = 0.08,
    min_reward_risk: float = 1.5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail-closed validation for a live Angel One F&O signal.

    AI may confirm or downgrade a deterministic candidate; it cannot reverse its
    direction. Only a fresh Angel WebSocket snapshot, fresh matching option quote,
    a risk-valid plan, and a fresh same-direction AI decision can PASS.
    """
    current = _datetime(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    blocks: list[str] = []
    checks: dict[str, bool] = {}
    strategy_decision = _decision(getattr(strategy, "decision", None))
    ai_decision = _decision(getattr(ai, "decision", None)) if ai is not None else ""

    checks["strategy_candidate"] = strategy_decision in {"CALL BUY", "PUT BUY"}
    if not checks["strategy_candidate"]:
        blocks.append("NO_QUALIFIED_STRATEGY_SIGNAL")

    guards = list(getattr(strategy, "guards", []) or []) if strategy is not None else []
    checks["strategy_guards_clear"] = not guards
    if guards:
        blocks.append("STRATEGY_GUARDS_PRESENT")

    try:
        strategy_confidence = float(getattr(strategy, "confidence", 0) or 0)
    except (TypeError, ValueError):
        strategy_confidence = 0
    checks["strategy_confidence"] = strategy_confidence >= min_strategy_confidence
    if not checks["strategy_confidence"]:
        blocks.append("STRATEGY_CONFIDENCE_TOO_LOW")

    snapshot_time = _datetime(getattr(snapshot, "timestamp", None)) if snapshot is not None else None
    market_age = (current - snapshot_time).total_seconds() if snapshot_time else None
    checks["snapshot_timestamp_valid"] = snapshot_time is not None and market_age is not None and market_age >= -2
    if not checks["snapshot_timestamp_valid"]:
        blocks.append("INVALID_MARKET_TIMESTAMP")
    checks["market_data_fresh"] = market_age is not None and -2 <= market_age <= max(1, stale_after_seconds)
    if not checks["market_data_fresh"]:
        blocks.append("STALE_MARKET_DATA")

    source = str(getattr(snapshot, "source", "") or "").strip().lower() if snapshot is not None else ""
    checks["websocket_source"] = source == "angel-one-websocket"
    if not checks["websocket_source"]:
        blocks.append("WEBSOCKET_SOURCE_REQUIRED")

    expected_side = "CE" if strategy_decision == "CALL BUY" else "PE" if strategy_decision == "PUT BUY" else ""
    strategy_side = str(getattr(strategy, "option_side", "") or "").upper() if strategy is not None else ""
    checks["option_side_matches_signal"] = bool(expected_side and strategy_side == expected_side)
    if not checks["option_side_matches_signal"]:
        blocks.append("SIGNAL_OPTION_SIDE_MISMATCH")

    try:
        strike = float(getattr(strategy, "strike", 0) or 0)
    except (TypeError, ValueError):
        strike = 0
    options = list(getattr(snapshot, "options", []) or []) if snapshot is not None else []
    matching = []
    for option in options:
        try:
            option_strike = float(getattr(option, "strike", 0) or 0)
        except (TypeError, ValueError):
            continue
        if str(getattr(option, "side", "") or "").upper() == expected_side and abs(option_strike - strike) <= 0.001:
            matching.append(option)
    selected = matching[0] if len(matching) == 1 else None
    checks["unique_option_quote"] = selected is not None
    if not checks["unique_option_quote"]:
        blocks.append("OPTION_QUOTE_NOT_UNIQUE")

    option_time = _datetime(getattr(selected, "timestamp", None)) if selected is not None else None
    option_age = (current - option_time).total_seconds() if option_time else None
    checks["option_quote_fresh"] = option_age is not None and -2 <= option_age <= max(1, stale_after_seconds)
    if not checks["option_quote_fresh"]:
        blocks.append("STALE_OPTION_QUOTE")

    bid = ask = ltp = None
    if selected is not None:
        try:
            bid = float(getattr(selected, "bid", 0) or 0)
            ask = float(getattr(selected, "ask", 0) or 0)
            ltp = float(getattr(selected, "ltp", 0) or 0)
        except (TypeError, ValueError):
            bid = ask = ltp = None
    quote_valid = bid is not None and ask is not None and ltp is not None and 0 < bid <= ask and ltp > 0
    checks["bid_ask_valid"] = bool(quote_valid)
    if not checks["bid_ask_valid"]:
        blocks.append("INVALID_BID_ASK")
    spread_fraction = ((ask - bid) / ((ask + bid) / 2)) if quote_valid else None
    checks["option_spread"] = spread_fraction is not None and spread_fraction <= max_spread_fraction
    if not checks["option_spread"]:
        blocks.append("OPTION_SPREAD_TOO_WIDE")

    try:
        entry = float(getattr(strategy, "entry", 0) or 0)
        stop = float(getattr(strategy, "stop_loss", 0) or 0)
        target = float(getattr(strategy, "target", 0) or 0)
    except (TypeError, ValueError):
        entry = stop = target = 0
    plan_valid = entry > stop > 0 and target > entry
    checks["entry_stop_target_order"] = plan_valid
    if not plan_valid:
        blocks.append("INVALID_ENTRY_SL_TARGET")
    rr = (target - entry) / (entry - stop) if plan_valid else None
    checks["reward_risk"] = rr is not None and rr >= min_reward_risk
    if not checks["reward_risk"]:
        blocks.append("REWARD_RISK_TOO_LOW")
    if quote_valid and entry > 0:
        checks["entry_near_live_quote"] = abs(ask - entry) / entry <= 0.15
    else:
        checks["entry_near_live_quote"] = False
    if not checks["entry_near_live_quote"]:
        blocks.append("ENTRY_DIFFERS_FROM_LIVE_ASK")

    checks["ai_available"] = ai is not None
    if ai is None:
        blocks.append("AI_NOT_VALIDATED")
    ai_time = _datetime(getattr(ai, "generated_at", None)) if ai is not None else None
    ai_age = (current - ai_time).total_seconds() if ai_time else None
    checks["ai_fresh"] = ai_age is not None and -2 <= ai_age <= max(90, stale_after_seconds * 4)
    if not checks["ai_fresh"]:
        blocks.append("AI_RESULT_STALE")
    checks["ai_direction_matches"] = bool(ai is not None and ai_decision == strategy_decision)
    if not checks["ai_direction_matches"]:
        blocks.append("AI_DIRECTION_MISMATCH")
    try:
        ai_confidence = float(getattr(ai, "confidence", 0) or 0) if ai is not None else 0
    except (TypeError, ValueError):
        ai_confidence = 0
    checks["ai_confidence"] = ai_confidence >= min_ai_confidence
    if not checks["ai_confidence"]:
        blocks.append("AI_CONFIDENCE_TOO_LOW")
    ai_action = str(getattr(ai, "action", "") or "").upper() if ai is not None else ""
    checks["ai_status_healthy"] = ai is not None and ai_action not in {"AI_ERROR", "AI_NOT_CONFIGURED", "SAFETY_BLOCK"}
    if not checks["ai_status_healthy"]:
        blocks.append("AI_STATUS_NOT_HEALTHY")
    ai_flags = list(getattr(ai, "risk_flags", []) or []) if ai is not None else []
    checks["ai_risk_flags_clear"] = not ai_flags
    if ai_flags:
        blocks.append("AI_RISK_FLAGS_PRESENT")

    unique_blocks = list(dict.fromkeys(blocks))
    passed = not unique_blocks
    return {
        "verdict": "PASS" if passed else "FAIL",
        "decision": strategy_decision if passed else "WAIT",
        "market_direction": (
            "BUY" if passed and strategy_decision == "CALL BUY"
            else "SELL" if passed and strategy_decision == "PUT BUY"
            else "WAIT"
        ),
        "strategy_decision": strategy_decision or "NO TRADE",
        "ai_decision": ai_decision or None,
        "blocks": unique_blocks,
        "checks": checks,
        "market_age_seconds": round(market_age, 2) if market_age is not None else None,
        "option_age_seconds": round(option_age, 2) if option_age is not None else None,
        "ai_age_seconds": round(ai_age, 2) if ai_age is not None else None,
        "spread_fraction": round(spread_fraction, 5) if spread_fraction is not None else None,
        "reward_risk": round(rr, 2) if rr is not None else None,
        "validated_at": current.isoformat(),
        "note": "AI may confirm or downgrade the deterministic signal; it cannot reverse the direction. FAIL means WAIT and blocks live execution.",
    }
