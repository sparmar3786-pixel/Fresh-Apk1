from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from statistics import mean, pstdev
from typing import Any

from backend.app.models import MarketSnapshot


def _status(status: str, **values: Any) -> dict[str, Any]:
    return {"status": status, **values}


def _direction(value: float, threshold: float = 0.0) -> str:
    if value > threshold:
        return "BULLISH"
    if value < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def _structure(candles: list[float]) -> dict[str, Any]:
    if len(candles) < 8:
        return _status("DATA_GAP", signal="NEUTRAL", reason="need at least 8 price observations")
    recent = candles[-4:]
    prior = candles[-8:-4]
    recent_high, recent_low = max(recent), min(recent)
    prior_high, prior_low = max(prior), min(prior)
    if recent_high > prior_high and recent_low > prior_low:
        return _status("AVAILABLE", signal="BULLISH", pattern="HH_HL", bos=True, choch=False)
    if recent_high < prior_high and recent_low < prior_low:
        return _status("AVAILABLE", signal="BEARISH", pattern="LH_LL", bos=True, choch=False)
    return _status("AVAILABLE", signal="NEUTRAL", pattern="RANGE", bos=False, choch=False)


def _liquidity_sweep(snapshot: MarketSnapshot, previous: MarketSnapshot | None) -> dict[str, Any]:
    if previous is None or snapshot.high is None or snapshot.low is None:
        return _status("DATA_GAP", signal="NEUTRAL", reason="previous OHLC snapshot required")
    prev_high = previous.high if previous.high is not None else previous.ltp
    prev_low = previous.low if previous.low is not None else previous.ltp
    sweep_high = snapshot.high > prev_high and snapshot.ltp < prev_high
    sweep_low = snapshot.low < prev_low and snapshot.ltp > prev_low
    signal = "BEARISH" if sweep_high and not sweep_low else "BULLISH" if sweep_low and not sweep_high else "NEUTRAL"
    return _status("AVAILABLE", signal=signal, high_sweep=sweep_high, low_sweep=sweep_low)


def _gap(snapshot: MarketSnapshot) -> dict[str, Any]:
    if snapshot.previous_close is None or snapshot.previous_close <= 0 or snapshot.open is None:
        return _status("DATA_GAP", signal="NEUTRAL", reason="open and previous close required")
    pct = (snapshot.open - snapshot.previous_close) / snapshot.previous_close * 100
    signal = "BULLISH" if pct > 0.20 else "BEARISH" if pct < -0.20 else "NEUTRAL"
    return _status("AVAILABLE", signal=signal, gap_pct=round(pct, 4), gap_fill_candidate=abs(pct) >= 0.5)


def _previous_profile(snapshot: MarketSnapshot, previous: MarketSnapshot | None) -> dict[str, Any]:
    if previous is None:
        return _status("DATA_GAP", signal="NEUTRAL", reason="previous session OHLC required")
    high = previous.high if previous.high is not None else previous.ltp
    low = previous.low if previous.low is not None else previous.ltp
    close = previous.ltp
    if snapshot.ltp > high:
        signal = "BULLISH"
    elif snapshot.ltp < low:
        signal = "BEARISH"
    elif snapshot.ltp > close:
        signal = "BULLISH"
    elif snapshot.ltp < close:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return _status("AVAILABLE", signal=signal, previous_high=high, previous_low=low, previous_close=close)


def _anchored_vwap(snapshot: MarketSnapshot, previous: MarketSnapshot | None) -> dict[str, Any]:
    if snapshot.vwap is None or snapshot.vwap <= 0:
        return _status("DATA_GAP", signal="NEUTRAL", reason="VWAP unavailable")
    deviation = (snapshot.ltp - snapshot.vwap) / snapshot.vwap * 100
    return _status(
        "AVAILABLE",
        signal="BULLISH" if deviation > 0.10 else "BEARISH" if deviation < -0.10 else "NEUTRAL",
        vwap=snapshot.vwap,
        deviation_pct=round(deviation, 4),
        anchor="session_vwap",
        swing_anchor_available=previous is not None,
    )


def _volume_profile(snapshot: MarketSnapshot) -> dict[str, Any]:
    # A real profile needs per-price/per-bar volume. Do not manufacture POC/HVN/LVN.
    if not snapshot.volume or snapshot.volume <= 0:
        return _status("NOT_AVAILABLE", signal="NEUTRAL", reason="volume profile feed unavailable")
    return _status("NOT_AVAILABLE", signal="NEUTRAL", reason="per-bar volume distribution required")


def _relative_strength(snapshot: MarketSnapshot, cross_index: dict[str, Any]) -> dict[str, Any]:
    if not cross_index:
        return _status("NOT_AVAILABLE", signal="NEUTRAL", reason="cross-index comparison unavailable")
    values = []
    for key, value in cross_index.items():
        if key == snapshot.index:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return _status("NOT_AVAILABLE", signal="NEUTRAL", reason="no comparable index bias")
    own = float(cross_index.get(snapshot.index, 0.0))
    relative = own - mean(values)
    return _status("AVAILABLE", signal=_direction(relative, 0.10), relative_score=round(relative, 4))


def _volatility(candles: list[float]) -> dict[str, Any]:
    if len(candles) < 20:
        return _status("DATA_GAP", signal="NEUTRAL", reason="need 20 prices")
    rets = [(b - a) / a for a, b in zip(candles[-20:-1], candles[-19:]) if a]
    if len(rets) < 5:
        return _status("DATA_GAP", signal="NEUTRAL", reason="insufficient returns")
    vol = pstdev(rets) if len(rets) > 1 else 0.0
    prior = candles[-40:-20]
    if len(prior) >= 10:
        prets = [(b - a) / a for a, b in zip(prior[:-1], prior[1:]) if a]
        prior_vol = pstdev(prets) if len(prets) > 1 else vol
    else:
        prior_vol = vol
    ratio = vol / prior_vol if prior_vol > 0 else 1.0
    signal = "BULLISH" if ratio > 1.35 and candles[-1] > candles[-2] else "BEARISH" if ratio > 1.35 and candles[-1] < candles[-2] else "NEUTRAL"
    regime = "EXPANSION" if ratio > 1.35 else "COMPRESSION" if ratio < 0.70 else "NORMAL"
    return _status("AVAILABLE", signal=signal, regime=regime, volatility_ratio=round(ratio, 4))


def _time_of_day(snapshot: MarketSnapshot) -> dict[str, Any]:
    ist = snapshot.timestamp.astimezone(timezone(timedelta(hours=5, minutes=30)))
    minutes = ist.hour * 60 + ist.minute
    if 555 <= minutes < 630:
        bucket = "OPENING"
    elif 630 <= minutes < 750:
        bucket = "MORNING"
    elif 750 <= minutes < 840:
        bucket = "MIDDAY"
    elif 840 <= minutes < 900:
        bucket = "CLOSING"
    else:
        bucket = "OUTSIDE_CORE"
    return _status("AVAILABLE", signal="NEUTRAL", bucket=bucket, ist_time=ist.strftime("%H:%M"))


def _anomaly(candles: list[float], snapshot: MarketSnapshot) -> dict[str, Any]:
    if len(candles) < 20:
        return _status("DATA_GAP", signal="NEUTRAL", reason="need 20 prices")
    window = candles[-20:]
    avg = mean(window)
    sd = pstdev(window)
    z = (snapshot.ltp - avg) / sd if sd > 0 else 0.0
    return _status("AVAILABLE", signal="BULLISH" if z > 2 else "BEARISH" if z < -2 else "NEUTRAL", price_z=round(z, 3), abnormal=abs(z) >= 2)


def _regime_transition(candles: list[float]) -> dict[str, Any]:
    if len(candles) < 40:
        return _status("DATA_GAP", signal="NEUTRAL", reason="need 40 prices")
    recent = candles[-10:]
    old = candles[-40:-30]
    recent_range = max(recent) - min(recent)
    old_range = max(old) - min(old)
    ratio = recent_range / old_range if old_range > 0 else 1.0
    direction = "BULLISH" if recent[-1] > recent[0] else "BEARISH" if recent[-1] < recent[0] else "NEUTRAL"
    return _status("AVAILABLE", signal=direction if ratio > 1.5 else "NEUTRAL", transition=ratio > 1.5, range_ratio=round(ratio, 3))


def _signal_decay(snapshot: MarketSnapshot, previous: MarketSnapshot | None) -> dict[str, Any]:
    if previous is None:
        return _status("DATA_GAP", signal="NEUTRAL", decay=0.0, reason="previous snapshot required")
    age = max(0.0, (snapshot.timestamp - previous.timestamp).total_seconds())
    price_move = abs(snapshot.ltp - previous.ltp) / previous.ltp if previous.ltp else 0.0
    decay = min(1.0, age / 300.0 + price_move / 0.01)
    return _status("AVAILABLE", signal="NEUTRAL", decay=round(decay, 3), stale=decay >= 1.0)


def _options_liquidity(snapshot: MarketSnapshot) -> dict[str, Any]:
    if not snapshot.options:
        return _status("DATA_GAP", signal="NEUTRAL", reason="option chain missing")
    spreads = []
    for o in snapshot.options:
        bid, ask = getattr(o, "bid", None), getattr(o, "ask", None)
        if bid is not None and ask is not None and o.ltp > 0:
            spreads.append(max(0.0, ask - bid) / o.ltp)
    if not spreads:
        return _status("NOT_AVAILABLE", signal="NEUTRAL", reason="bid/ask feed unavailable")
    avg_spread = mean(spreads)
    return _status("AVAILABLE", signal="NEUTRAL", average_relative_spread=round(avg_spread, 4), low_liquidity=avg_spread > 0.05)


def _vote(modules: dict[str, dict[str, Any]]) -> dict[str, Any]:
    weights = {
        "liquidity_sweep": 1.0, "market_structure": 1.3, "gap": 0.8,
        "previous_day_profile": 1.0, "anchored_vwap": 1.1, "relative_strength": 0.8,
        "volatility_regime": 0.7, "time_of_day": 0.2, "anomaly": 0.5,
        "regime_transition": 1.0,
    }
    score = 0.0
    used = 0.0
    for name, weight in weights.items():
        row = modules.get(name, {})
        if row.get("status") != "AVAILABLE":
            continue
        signal = row.get("signal")
        if signal == "BULLISH":
            score += weight
        elif signal == "BEARISH":
            score -= weight
        used += weight
    normalized = score / used if used else 0.0
    return {"direction": _direction(normalized, 0.15), "score": round(normalized, 4), "votes_used": round(used, 2)}


def evaluate_adaptive_intelligence(
    snapshot: MarketSnapshot,
    previous: MarketSnapshot | None = None,
    cross_index: dict[str, Any] | None = None,
    memory: Any = None,
) -> dict[str, Any]:
    candles = list(snapshot.candles or [])
    modules = {
        "liquidity_sweep": _liquidity_sweep(snapshot, previous),
        "market_structure": _structure(candles),
        "gap": _gap(snapshot),
        "previous_day_profile": _previous_profile(snapshot, previous),
        "anchored_vwap": _anchored_vwap(snapshot, previous),
        "volume_profile": _volume_profile(snapshot),
        "relative_strength": _relative_strength(snapshot, cross_index or {}),
        "sector_rotation": _status("NOT_AVAILABLE", signal="NEUTRAL", reason="sector breadth/feed not attached"),
        "breadth": _status("NOT_AVAILABLE", signal="NEUTRAL", reason="advance/decline breadth feed not attached"),
        "intermarket": _status("NOT_AVAILABLE", signal="NEUTRAL", reason="intermarket feed not attached"),
        "volatility_regime": _volatility(candles),
        "expiry_behaviour": _status("NOT_AVAILABLE", signal="NEUTRAL", reason="expiry metadata not attached"),
        "time_of_day": _time_of_day(snapshot),
        "event_risk": _status("NOT_AVAILABLE", signal="NEUTRAL", reason="event calendar feed not attached"),
        "anomaly": _anomaly(candles, snapshot),
        "regime_transition": _regime_transition(candles),
        "signal_decay": _signal_decay(snapshot, previous),
        "options_liquidity": _options_liquidity(snapshot),
    }
    vote = _vote(modules)
    signal_decay = modules["signal_decay"]
    if signal_decay.get("stale"):
        vote = {**vote, "direction": "NEUTRAL", "score": 0.0, "guard": "SIGNAL_DECAY"}
    if modules["options_liquidity"].get("low_liquidity"):
        vote = {**vote, "direction": "NEUTRAL", "guard": "LOW_LIQUIDITY"}

    # Strategy voting is deliberately deterministic. Memory may later supply
    # regime-specific weights, but absence of memory never creates an edge.
    allocator = _status(
        "AVAILABLE" if memory is not None else "NOT_AVAILABLE",
        mode="regime_weighted",
        note="strategy weights can be learned from closed trades; no live edge is invented",
    )
    modules["meta_strategy"] = {
        "status": "AVAILABLE",
        "direction": vote["direction"],
        "score": vote["score"],
        "method": "weighted multi-module voting",
    }
    modules["online_allocator"] = allocator

    available_count = sum(row.get("status") == "AVAILABLE" for row in modules.values())
    unavailable_count = sum(row.get("status") in {"DATA_GAP", "NOT_AVAILABLE"} for row in modules.values())
    feed_health = round(100.0 * available_count / max(1, len(modules)), 1)
    # This is a heuristic strength score, not a statistically calibrated probability.
    heuristic_strength = round(min(99.0, max(1.0, 50.0 + abs(vote["score"]) * 40.0)), 1)
    hard_guards = []
    if snapshot.ltp <= 0 or not isfinite(float(snapshot.ltp)):
        hard_guards.append("INVALID_SPOT_PRICE")
    if snapshot.timestamp.tzinfo is None:
        hard_guards.append("NAIVE_TIMESTAMP")
    age_sec = max(0.0, (datetime.now(timezone.utc) - snapshot.timestamp.astimezone(timezone.utc)).total_seconds()) if snapshot.timestamp.tzinfo else 0.0
    if age_sec > 15:
        hard_guards.append("STALE_SNAPSHOT")
    if len(candles) < 20:
        hard_guards.append("INSUFFICIENT_PRICE_HISTORY")
    if hard_guards:
        vote = {**vote, "direction": "NEUTRAL", "score": 0.0, "guard": hard_guards[0]}
    brief = {
        "index": snapshot.index,
        "spot": snapshot.ltp,
        "decision_context": {
            "direction": vote["direction"],
            "score": vote["score"],
            "heuristic_strength": heuristic_strength,
            "confidence_is_calibrated": False,
            "feed_health_pct": feed_health,
            "available_module_count": available_count,
            "missing_module_count": unavailable_count,
            "snapshot_age_sec": round(age_sec, 2),
            "hard_guards": hard_guards,
            "trade_gate": "BLOCK" if "guard" in vote else "OPEN_FOR_EXISTING_RISK_GATES",
            "top_signals": [
                {"module": name, "signal": row.get("signal"), "status": row.get("status")}
                for name, row in modules.items()
                if row.get("status") == "AVAILABLE" and row.get("signal") in {"BULLISH", "BEARISH"}
            ][:6],
            "data_gaps": [
                {"module": name, "reason": row.get("reason", "")}
                for name, row in modules.items()
                if row.get("status") in {"DATA_GAP", "NOT_AVAILABLE"}
            ][:8],
        },
        "risk_instruction": "AI may explain, rank and flag contradictions; deterministic risk/data-quality gates remain authoritative.",
        "request": "Return concise confirmation, contradiction flags, invalidation and scenario summary. Do not invent missing market data.",
    }
    return {
        "modules": modules,
        "decision_vote": vote,
        "confidence": heuristic_strength,
        "confidence_is_calibrated": False,
        "feed_health_pct": feed_health,
        "hard_guards": hard_guards,
        "ai_brief": brief,
    }
