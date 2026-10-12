"""Lightweight, broker-agnostic strategy confluence layer for Fresh-Apk.

Inspired by research patterns catalogued in awesome-systematic-trading and
awesome-ai-in-finance, and by the market-replay realism principles in
hftbacktest. This is an original implementation, not a copy of those projects.
It does not place orders and does not replace Angel One market-data validation.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .research_strategy_pack import evaluate_research_pack


def _number(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if isfinite(n) else None


def _timeframe_direction(rows: Any) -> str:
    """Infer direction only from a usable series of closes; otherwise UNKNOWN."""
    if not isinstance(rows, list) or len(rows) < 3:
        return "UNKNOWN"
    closes: list[float] = []
    for row in rows[-5:]:
        if not isinstance(row, dict):
            continue
        value = next((row.get(k) for k in ("close", "ltp", "price", "c") if row.get(k) is not None), None)
        number = _number(value)
        if number is not None and number > 0:
            closes.append(number)
    if len(closes) < 3:
        return "UNKNOWN"
    first, previous, latest = closes[0], closes[-2], closes[-1]
    if latest > previous and latest > first:
        return "BULLISH"
    if latest < previous and latest < first:
        return "BEARISH"
    return "MIXED"


def evaluate_confluence(
    snapshot: Any,
    candidate: str,
    indicators: dict[str, Any] | None = None,
    selected_option: Any = None,
) -> dict[str, Any]:
    """Return transparent confluence diagnostics without inventing a trade.

    Candidate is CALL BUY / PUT BUY / WAIT. Score is a research-quality measure,
    not a probability of profit. Missing fields are neutral, never imputed.
    """
    candidate = str(getattr(candidate, "value", candidate) or "").upper()
    direction = "BULLISH" if candidate == "CALL BUY" else "BEARISH" if candidate == "PUT BUY" else "UNKNOWN"
    indicators = indicators or {}
    checks: dict[str, str] = {}
    score = 0
    known = 0

    def add(name: str, state: str, points: int = 0) -> None:
        nonlocal score, known
        checks[name] = state
        if state != "UNKNOWN":
            known += 1
            score += points

    fast = _number(indicators.get("ema_fast"))
    slow = _number(indicators.get("ema_slow"))
    if fast is None or slow is None:
        add("ema_trend", "UNKNOWN")
    else:
        trend = "BULLISH" if fast > slow else "BEARISH" if fast < slow else "MIXED"
        add("ema_trend", trend, 2 if trend == direction else -2 if trend in {"BULLISH", "BEARISH"} else 0)

    macd_hist = _number(indicators.get("macd_hist"))
    if macd_hist is None:
        add("macd_momentum", "UNKNOWN")
    else:
        trend = "BULLISH" if macd_hist > 0 else "BEARISH" if macd_hist < 0 else "MIXED"
        add("macd_momentum", trend, 2 if trend == direction else -2 if trend in {"BULLISH", "BEARISH"} else 0)

    rsi = _number(indicators.get("rsi14"))
    if rsi is None:
        add("rsi_momentum", "UNKNOWN")
    else:
        trend = "BULLISH" if rsi >= 55 else "BEARISH" if rsi <= 45 else "MIXED"
        add("rsi_momentum", trend, 1 if trend == direction else -1 if trend in {"BULLISH", "BEARISH"} else 0)

    timeframes = getattr(snapshot, "timeframes", {}) or {}
    timeframe_states: dict[str, str] = {}
    if isinstance(timeframes, dict):
        for name, rows in timeframes.items():
            state = _timeframe_direction(rows)
            timeframe_states[str(name)] = state
            if state in {"BULLISH", "BEARISH"}:
                known += 1
                score += 2 if state == direction else -2

    if timeframe_states:
        checks["multi_timeframe"] = "UNKNOWN" if all(v == "UNKNOWN" for v in timeframe_states.values()) else (
            "ALIGNED" if any(v == direction for v in timeframe_states.values())
            and not any(v in {"BULLISH", "BEARISH"} and v != direction for v in timeframe_states.values())
            else "CONFLICT" if any(v in {"BULLISH", "BEARISH"} and v != direction for v in timeframe_states.values())
            else "MIXED"
        )
    else:
        checks["multi_timeframe"] = "UNKNOWN"

    if selected_option is not None:
        bid = _number(getattr(selected_option, "bid", None))
        ask = _number(getattr(selected_option, "ask", None))
        ltp = _number(getattr(selected_option, "ltp", None))
        if bid is not None and ask is not None and ltp is not None and 0 < bid <= ltp <= ask:
            spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
            checks["option_liquidity"] = "TIGHT" if spread_pct <= 2 else "WIDE" if spread_pct > 8 else "MODERATE"
            known += 1
            score += 1 if spread_pct <= 2 else -1 if spread_pct > 8 else 0
        else:
            checks["option_liquidity"] = "UNKNOWN"
    else:
        checks["option_liquidity"] = "UNKNOWN"

    options = list(getattr(snapshot, "options", []) or [])
    if options:
        call_flow = sum((_number(getattr(o, "oi_change", 0)) or 0) for o in options if str(getattr(o, "side", "")).upper() == "CE")
        put_flow = sum((_number(getattr(o, "oi_change", 0)) or 0) for o in options if str(getattr(o, "side", "")).upper() == "PE")
        if call_flow == put_flow:
            flow = "BALANCED"
        elif call_flow > put_flow:
            flow = "CALL_OI_CHANGE_DOMINANT"
        else:
            flow = "PUT_OI_CHANGE_DOMINANT"
        checks["oi_flow"] = flow
    else:
        checks["oi_flow"] = "UNKNOWN"

    # Normalize a transparent evidence score; it is not a win-rate estimate.
    normalized = round(max(0.0, min(100.0, 50.0 + score * 5.0)), 1) if known else None
    research_pack = evaluate_research_pack(snapshot, candidate, indicators, selected_option)
    return {
        "candidate_direction": direction,
        "confluence_score": normalized,
        "score_meaning": "Evidence alignment score, not a probability of profit",
        "checks": checks,
        "timeframes": timeframe_states,
        "known_evidence_count": known,
        "research_pack": research_pack,
    }
