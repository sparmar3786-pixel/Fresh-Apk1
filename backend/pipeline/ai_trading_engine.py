"""Multi-timeframe paper-trading decision engine.

The module is deterministic by design: AI may enrich the explanation, but it never
bypasses market-data, timeframe, liquidity, risk or exit gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from backend.pipeline.trade_management import build_option_levels

TIMEFRAME_ORDER = ("15m", "5m", "1m")


def _clean(values: list[float] | None) -> list[float]:
    out: list[float] = []
    for value in values or []:
        try:
            n = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(n) and n > 0:
            out.append(n)
    return out


def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
    return current


def _atr_proxy(values: list[float], period: int = 14) -> float:
    clean = _clean(values)
    if len(clean) < 2:
        return 0.0
    diffs = [abs(b - a) for a, b in zip(clean, clean[1:])]
    sample = diffs[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def _trend(values: list[float]) -> dict[str, Any]:
    clean = _clean(values)
    if len(clean) < 25:
        return {"ready": False, "direction": "MIXED", "score": 0.0, "atr": _atr_proxy(clean)}
    fast = _ema(clean, 8) or clean[-1]
    slow = _ema(clean, 21) or clean[-1]
    lookback = clean[-6]
    slope = (clean[-1] - lookback) / max(abs(lookback), 1e-9)
    direction = "BULLISH" if fast > slow and slope > 0 else "BEARISH" if fast < slow and slope < 0 else "MIXED"
    distance = (fast - slow) / max(abs(clean[-1]), 1e-9)
    score = max(-1.0, min(1.0, distance * 40.0 + slope * 30.0))
    return {
        "ready": True,
        "direction": direction,
        "score": round(score, 4),
        "ema8": round(fast, 4),
        "ema21": round(slow, 4),
        "slope": round(slope, 6),
        "atr": round(_atr_proxy(clean), 4),
    }


def evaluate_multi_timeframe(timeframes: dict[str, list[float]], side: str) -> dict[str, Any]:
    side = side.upper()
    if side not in {"CE", "PE"}:
        return {"eligible": False, "blocks": ["INVALID_SIDE"]}
    stats = {tf: _trend(timeframes.get(tf)) for tf in TIMEFRAME_ORDER}
    blocks: list[str] = []
    missing = [tf for tf in TIMEFRAME_ORDER if not stats[tf]["ready"]]
    if missing:
        blocks.append("INSUFFICIENT_" + "_".join(missing).upper())

    def aligned(tf: str) -> bool:
        wanted = "BULLISH" if side == "CE" else "BEARISH"
        return stats[tf]["direction"] == wanted

    if not missing and not aligned("15m"):
        blocks.append("REGIME_NOT_ALIGNED")
    if not missing and not aligned("5m"):
        blocks.append("SETUP_NOT_ALIGNED")
    if not missing and not aligned("1m"):
        blocks.append("TRIGGER_NOT_ALIGNED")

    recent = _clean(timeframes.get("1m"))
    trigger = False
    if len(recent) >= 6:
        wanted_bull = side == "CE"
        recent_move = recent[-1] - recent[-4]
        trigger = recent_move > 0 if wanted_bull else recent_move < 0
        trigger = trigger and (recent[-1] > (_ema(recent, 8) or recent[-1]) if wanted_bull else recent[-1] < (_ema(recent, 8) or recent[-1]))
    if not missing and not trigger:
        blocks.append("TRIGGER_NOT_CONFIRMED")

    alignment_bonus = sum(1 for tf in TIMEFRAME_ORDER if not missing and aligned(tf)) * 15
    trigger_bonus = 5 if trigger else 0
    confidence = min(99, 45 + alignment_bonus + trigger_bonus)
    wanted = "BULLISH" if side == "CE" else "BEARISH"
    regime = "BULLISH" if wanted == "BULLISH" and all(not missing and aligned(tf) for tf in TIMEFRAME_ORDER) else "BEARISH" if wanted == "BEARISH" and all(not missing and aligned(tf) for tf in TIMEFRAME_ORDER) else stats["15m"]["direction"]
    eligible = not blocks and confidence >= 70
    return {
        "eligible": eligible,
        "side": side,
        "regime": regime,
        "regime_timeframe": "15m",
        "setup_timeframe": "5m",
        "entry_timeframe": "1m",
        "confidence": float(confidence),
        "blocks": blocks,
        "timeframes": stats,
        "atr": stats["5m"]["atr"] if stats["5m"]["atr"] > 0 else stats["15m"]["atr"],
        "trigger_price": recent[-1] if recent else None,
        "invalidation_price": (
            min(recent[-5:]) if side == "CE" and len(recent) >= 5 else
            max(recent[-5:]) if side == "PE" and len(recent) >= 5 else None
        ),
    }


def _spread(option: dict[str, Any]) -> float | None:
    try:
        bid, ask, ltp = float(option["bid"]), float(option["ask"]), float(option["ltp"])
    except (KeyError, TypeError, ValueError):
        return None
    if ltp <= 0 or ask < bid:
        return None
    return (ask - bid) / ltp


def choose_strike(options: list[dict[str, Any]], side: str, atm: float) -> dict[str, Any]:
    side = side.upper()
    candidates = [o for o in options if str(o.get("side", "")).upper() == side and float(o.get("ltp", 0) or 0) > 0]
    if not candidates:
        raise ValueError("NO_OPTION_CANDIDATE")

    def score(o: dict[str, Any]) -> float:
        strike = abs(float(o.get("strike", atm)) - atm) / max(atm, 1.0)
        delta = o.get("delta")
        delta_penalty = abs(abs(float(delta)) - 0.5) if delta is not None else 0.25
        spread = _spread(o)
        spread_penalty = min(1.0, spread * 8) if spread is not None else 0.8
        volume = max(0.0, float(o.get("volume", 0) or 0))
        oi = max(0.0, float(o.get("oi", 0) or 0))
        liquidity_penalty = 1.0 / (1.0 + volume / 50000.0) + 1.0 / (1.0 + oi / 200000.0)
        dte_raw = o.get("dte")
        dte_penalty = 0.0
        if dte_raw is not None:
            try:
                dte = max(0.0, float(dte_raw))
                dte_penalty = 0.08 if dte == 0 else 0.03 if dte == 1 else 0.0
            except (TypeError, ValueError):
                dte_penalty = 0.05
        return delta_penalty * 4.0 + spread_penalty * 2.5 + liquidity_penalty * 0.8 + strike * 8.0 + dte_penalty * 10.0

    ranked = sorted(candidates, key=score)
    chosen = dict(ranked[0])
    s = score(chosen)
    chosen["quality_score"] = round(s, 4)
    chosen["selection_grade"] = "A+" if s < 1.5 else "A" if s < 2.5 else "B" if s < 4 else "C"
    chosen["selection_reason"] = "Prefer delta near 0.50, tight spread, high liquidity/OI, ATM proximity and usable DTE."
    return chosen


def build_trade_plan(
    *,
    index: str,
    side: str,
    strike: float,
    option: dict[str, Any],
    timeframe: dict[str, Any],
    now: datetime | None = None,
    minutes_to_session_close: float = 120,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    levels = build_option_levels(
        ltp=float(option.get("ltp", 0) or 0),
        bid=option.get("bid"),
        ask=option.get("ask"),
        stop_pct=0.12,
        min_rr=1.5,
        tick_size=float(option.get("tick_size", 0.05) or 0.05),
    )
    if not levels.get("ok"):
        return {"eligible": False, "reason": levels.get("reason", "INVALID_OPTION_LEVELS")}
    entry = float(levels["entry"])
    risk = float(levels["risk_per_unit"])
    target1 = round(entry + risk * 1.5, 2)
    target2 = round(entry + risk * 2.5, 2)
    target3 = round(entry + risk * 3.5, 2)
    time_exit = min(45, max(15, int(minutes_to_session_close - 5)))
    return {
        "eligible": bool(timeframe.get("eligible")),
        "index": index,
        "side": side.upper(),
        "strike": float(strike),
        "symbol": option.get("symbol"),
        "entry": entry,
        "entry_basis": levels["entry_basis"],
        "execution_ready": bool(levels["execution_ready"]),
        "bid": levels["bid"],
        "ask": levels["ask"],
        "spread_pct": levels["spread_pct"],
        "stop_loss": levels["stop_loss"],
        "risk_per_unit": risk,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "rr_target1": round((target1 - entry) / risk, 2),
        "rr_target2": round((target2 - entry) / risk, 2),
        "rr_target3": round((target3 - entry) / risk, 2),
        "underlying_trigger_price": timeframe.get("trigger_price"),
        "underlying_invalidation": timeframe.get("invalidation_price"),
        "entry_timeframe": timeframe.get("entry_timeframe", "1m"),
        "setup_timeframe": timeframe.get("setup_timeframe", "5m"),
        "regime_timeframe": timeframe.get("regime_timeframe", "15m"),
        "regime": timeframe.get("regime", "MIXED"),
        "confidence": timeframe.get("confidence", 0),
        "selection_grade": option.get("selection_grade"),
        "selection_quality_score": option.get("quality_score"),
        "selection_reason": option.get("selection_reason"),
        "dte": option.get("dte"),
        "lot_size": option.get("lot_size"),
        "tick_size": option.get("tick_size") or 0.05,
        "time_exit_minutes": time_exit,
        "trail_after_target1": "Move SL toward entry; then trail behind 1m/5m structure.",
        "exit_rules": [
            "EXIT_STOP when option LTP <= stop loss.",
            "PARTIAL_EXIT at target1; trail remaining position.",
            "PARTIAL_EXIT at target2; keep runner for target3 only while 5m trend remains aligned.",
            "EXIT_TARGET3 when target3 is reached.",
            "EXIT_SIGNAL_FLIP when 5m + 15m direction invalidates the trade.",
            "EXIT_TIME when the configured intraday time stop is reached.",
            "EXIT_DATA_GUARD immediately on stale feed, crossed quote or missing critical data.",
        ],
        "opened_at": now.isoformat(),
        "advisory_only": True,
        "live_order_placement": False,
    }


def evaluate_exit(position: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    ltp = float(position.get("ltp", 0) or 0)
    if ltp <= 0:
        return {"action": "EXIT_DATA_GUARD", "reason": "invalid_live_premium"}
    if ltp <= float(position.get("stop_loss", 0) or 0):
        return {"action": "EXIT_STOP", "reason": "premium_at_or_below_stop"}
    if ltp >= float(position.get("target3", float("inf"))):
        return {"action": "EXIT_TARGET3", "reason": "third_target_reached"}
    if ltp >= float(position.get("target2", float("inf"))):
        return {"action": "PARTIAL_T2", "reason": "second_target_reached"}
    if ltp >= float(position.get("target1", float("inf"))):
        return {"action": "TRAIL_AFTER_T1", "reason": "first_target_reached"}
    if str(position.get("signal_side", position.get("side", ""))).upper() != str(position.get("side", "")).upper():
        return {"action": "EXIT_SIGNAL_FLIP", "reason": "directional_signal_flipped"}
    opened = position.get("opened_at")
    if opened:
        try:
            started = datetime.fromisoformat(str(opened).replace("Z", "+00:00"))
            minutes = (now - started).total_seconds() / 60.0
            if minutes >= float(position.get("time_exit_minutes", 30) or 30):
                return {"action": "EXIT_TIME", "reason": "intraday_time_stop_reached"}
        except ValueError:
            pass
    return {"action": "HOLD", "reason": "no exit trigger"}
