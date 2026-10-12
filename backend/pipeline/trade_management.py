"""Deterministic option trade-plan helpers; advisory only, never submits orders."""
from __future__ import annotations

import math
from typing import Any


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def build_option_levels(
    *,
    ltp: float | None,
    bid: float | None,
    ask: float | None,
    stop_pct: float = 0.12,
    min_rr: float = 1.8,
    tick_size: float = 0.05,
) -> dict[str, Any]:
    """Build premium-denominated levels and label whether entry is executable."""
    last = _positive(ltp)
    b, a = _positive(bid), _positive(ask)
    if last is None:
        return {"ok": False, "reason": "missing_or_invalid_ltp"}
    if not (0 < stop_pct < 1) or min_rr < 1 or tick_size <= 0:
        return {"ok": False, "reason": "invalid_risk_configuration"}
    quote_valid = b is not None and a is not None and a >= b
    if b is not None and a is not None and a < b:
        return {"ok": False, "reason": "crossed_quote"}
    entry = a if quote_valid else last
    spread_pct = (a - b) / entry if quote_valid else None
    if spread_pct is not None and spread_pct > 0.05:
        return {"ok": False, "reason": "wide_spread", "spread_pct": round(spread_pct, 4)}
    risk = max(entry * stop_pct, tick_size)
    tick = lambda x: round(round(x / tick_size) * tick_size, 2)
    stop = tick(max(tick_size, entry - risk))
    actual_risk = round(entry - stop, 2)
    if actual_risk <= 0:
        return {"ok": False, "reason": "invalid_stop_distance"}
    target1 = tick(entry + actual_risk * min_rr)
    target2 = tick(entry + actual_risk * max(2.0, min_rr + 0.2))
    return {
        "ok": True,
        "entry": round(entry, 2),
        "entry_basis": "best_ask" if quote_valid else "ltp_reference",
        "execution_ready": quote_valid,
        "bid": b,
        "ask": a,
        "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
        "stop_loss": stop,
        "risk_per_unit": actual_risk,
        "target1": target1,
        "target2": target2,
        "rr_target1": round((target1 - entry) / actual_risk, 2),
        "rr_target2": round((target2 - entry) / actual_risk, 2),
        "trail_after_target1": True,
        "time_exit_required": True,
    }


def strike_quality(row: dict[str, Any], side: str, atm: float, step: float) -> tuple[float, dict[str, Any]]:
    """Lower score is better: prefer ~0.50 absolute delta, tighter spread, more volume."""
    key = "ce" if side.upper() == "CE" else "pe"
    strike = _positive(row.get("strike"))
    ltp = _positive(row.get(f"{key}_ltp"))
    delta = row.get(f"{key}_delta")
    bid, ask = _positive(row.get(f"{key}_bid")), _positive(row.get(f"{key}_ask"))
    volume = max(0.0, float(row.get(f"{key}_volume") or 0))
    if strike is None or ltp is None:
        return float("inf"), {"eligible": False, "reason": "missing_strike_or_premium"}
    distance = abs(strike - atm) / max(step, 0.01)
    delta_penalty = abs(abs(float(delta)) - 0.5) * 4 if delta is not None else 0.75
    spread_penalty = ((ask - bid) / ltp * 10) if bid is not None and ask is not None and ask >= bid else 1.0
    volume_penalty = 1.0 / (1.0 + volume / 1000.0)
    score = distance * 0.25 + delta_penalty + spread_penalty + volume_penalty
    return score, {
        "eligible": True,
        "strike_distance_steps": round(distance, 2),
        "abs_delta": abs(float(delta)) if delta is not None else None,
        "spread_pct": round((ask - bid) / ltp, 4) if bid is not None and ask is not None and ask >= bid else None,
        "volume": volume,
        "quality_score": round(score, 4),
    }


def size_in_lots(
    *, capital_inr: float | None, risk_fraction: float, entry: float,
    stop_loss: float, lot_size: int | None,
) -> dict[str, Any]:
    """Only size when account capital and current exchange lot size are explicitly supplied."""
    if capital_inr is None or capital_inr <= 0:
        return {"quantity": None, "lots": None, "status": "capital_not_configured"}
    if lot_size is None or lot_size <= 0:
        return {"quantity": None, "lots": None, "status": "verified_lot_size_missing"}
    per_unit = entry - stop_loss
    if per_unit <= 0 or not 0 < risk_fraction <= 0.02:
        return {"quantity": None, "lots": None, "status": "invalid_risk_inputs"}
    risk_budget = capital_inr * risk_fraction
    lots = int(risk_budget // (per_unit * lot_size))
    return {
        "quantity": lots * lot_size,
        "lots": lots,
        "risk_budget_inr": round(risk_budget, 2),
        "estimated_max_loss_inr": round(lots * lot_size * per_unit, 2),
        "status": "sized" if lots > 0 else "risk_budget_below_one_lot",
    }
