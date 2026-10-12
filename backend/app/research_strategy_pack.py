"""Research-inspired, broker-neutral strategy pack for Fresh Algo Signal.

This is an original adaptation of general ideas from systematic-trading and
AI-finance research lists. It is not copied source code from the referenced
projects and never places orders. Unknown inputs remain UNKNOWN.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _side(value: Any) -> str:
    return str(getattr(value, "side", "") or "").upper()


def evaluate_research_pack(
    snapshot: Any,
    candidate: str,
    indicators: dict[str, Any] | None = None,
    selected_option: Any = None,
) -> dict[str, Any]:
    """Evaluate complementary trend, reversion, option-flow and execution checks.

    The evidence score is not a probability, return forecast, or guarantee.
    Outputs are diagnostic and should be used with Fresh's existing stale-data,
    risk, and live-AI validation gates.
    """
    candidate = str(getattr(candidate, "value", candidate) or "").upper()
    direction = "BULLISH" if candidate == "CALL BUY" else "BEARISH" if candidate == "PUT BUY" else "UNKNOWN"
    ind = indicators or {}
    checks: dict[str, dict[str, Any]] = {}
    directional_votes: list[tuple[str, int, float]] = []

    fast, slow = _num(ind.get("ema_fast")), _num(ind.get("ema_slow"))
    macd_hist = _num(ind.get("macd_hist"))
    if fast is not None and slow is not None and macd_hist is not None:
        vote = 1 if fast > slow and macd_hist > 0 else -1 if fast < slow and macd_hist < 0 else 0
        checks["trend_following"] = {
            "state": "BULLISH" if vote > 0 else "BEARISH" if vote < 0 else "MIXED",
            "inputs": {"ema_fast": fast, "ema_slow": slow, "macd_hist": macd_hist},
            "reason": "EMA trend and MACD histogram must agree",
        }
        if vote:
            directional_votes.append(("trend_following", vote, 2.0))
    else:
        checks["trend_following"] = {"state": "UNKNOWN", "reason": "EMA and MACD inputs required"}

    rsi, zscore = _num(ind.get("rsi14")), _num(ind.get("zscore20"))
    if rsi is not None and zscore is not None:
        vote = 1 if rsi <= 30 and zscore <= -2 else -1 if rsi >= 70 and zscore >= 2 else 0
        state = "OVERSOLD_REVERSAL_WATCH" if vote > 0 else "OVERBOUGHT_REVERSAL_WATCH" if vote < 0 else "NO_EXTREME"
        checks["mean_reversion"] = {
            "state": state,
            "inputs": {"rsi14": rsi, "zscore20": zscore},
            "reason": "Requires both RSI extreme and price z-score extreme; watch only, not an entry trigger",
        }
        if vote:
            directional_votes.append(("mean_reversion", vote, 1.0))
    else:
        checks["mean_reversion"] = {"state": "UNKNOWN", "reason": "RSI and z-score required"}

    options = list(getattr(snapshot, "options", []) or [])
    flow_counts = {"CE_LONG_BUILDUP": 0, "CE_SHORT_BUILDUP": 0, "CE_SHORT_COVERING": 0,
                   "CE_LONG_UNWINDING": 0, "PE_LONG_BUILDUP": 0, "PE_SHORT_BUILDUP": 0,
                   "PE_SHORT_COVERING": 0, "PE_LONG_UNWINDING": 0}
    ce_pressure = 0.0
    pe_pressure = 0.0
    known_flow = 0
    for option in options:
        side = _side(option)
        oi_change = _num(getattr(option, "oi_change", None))
        premium_change = _num(getattr(option, "premium_change", None))
        if side not in {"CE", "PE"} or oi_change is None or premium_change is None:
            continue
        if premium_change > 0 and oi_change > 0:
            regime = "LONG_BUILDUP"
        elif premium_change < 0 and oi_change > 0:
            regime = "SHORT_BUILDUP"
        elif premium_change > 0 and oi_change < 0:
            regime = "SHORT_COVERING"
        elif premium_change < 0 and oi_change < 0:
            regime = "LONG_UNWINDING"
        else:
            continue
        flow_counts[f"{side}_{regime}"] += 1
        known_flow += 1
        # A cautious heuristic only: call-side strengthening leans bullish;
        # put-side strengthening leans bearish, with the regime retained as evidence.
        signed = 1.0 if regime in {"LONG_BUILDUP", "SHORT_COVERING"} else -1.0
        if side == "CE":
            ce_pressure += signed
        else:
            pe_pressure += signed
    if known_flow:
        flow_score = ce_pressure - pe_pressure
        vote = 1 if flow_score > 0 else -1 if flow_score < 0 else 0
        checks["option_oi_premium_flow"] = {
            "state": "BULLISH_LEAN" if vote > 0 else "BEARISH_LEAN" if vote < 0 else "BALANCED",
            "observations": known_flow,
            "classification_counts": flow_counts,
            "reason": "Heuristic CE/PE premium-plus-OI classification; validate against spot trend and full chain",
        }
        if vote:
            directional_votes.append(("option_oi_premium_flow", vote, 1.5))
    else:
        checks["option_oi_premium_flow"] = {
            "state": "UNKNOWN", "observations": 0, "classification_counts": flow_counts,
            "reason": "Premium change and OI change required on option rows",
        }

    bid = _num(getattr(selected_option, "bid", None)) if selected_option is not None else None
    ask = _num(getattr(selected_option, "ask", None)) if selected_option is not None else None
    ltp = _num(getattr(selected_option, "ltp", None)) if selected_option is not None else None
    volume = _num(getattr(selected_option, "volume", None)) if selected_option is not None else None
    if bid is not None and ask is not None and ltp is not None and 0 < bid <= ask and bid <= ltp <= ask:
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        state = "TIGHT" if spread_pct <= 2 else "MODERATE" if spread_pct <= 8 else "WIDE"
        checks["execution_liquidity"] = {
            "state": state, "spread_pct": round(spread_pct, 3), "volume": volume,
            "reason": "Spread is a liquidity proxy, not a fill/latency simulation",
        }
    else:
        checks["execution_liquidity"] = {
            "state": "UNKNOWN", "spread_pct": None, "volume": volume,
            "reason": "Valid bid, ask and LTP are required; no values are imputed",
        }

    known = [(name, vote, weight) for name, vote, weight in directional_votes]
    weighted = sum(vote * weight for _, vote, weight in known)
    total_weight = sum(weight for _, _, weight in known)
    alignment = "UNKNOWN" if not known or direction == "UNKNOWN" else (
        "ALIGNED" if weighted > 0 and direction == "BULLISH" or weighted < 0 and direction == "BEARISH"
        else "CONFLICT" if weighted != 0 else "MIXED"
    )
    score = round(50 + 50 * weighted / total_weight, 1) if total_weight else None
    return {
        "version": "research-pack-v1",
        "candidate_direction": direction,
        "candidate_alignment": alignment,
        "evidence_score": score,
        "score_meaning": "Research evidence alignment only; not probability of profit",
        "known_directional_checks": len(known),
        "checks": checks,
        "safety_note": "Diagnostics only. Existing freshness, risk and live-AI validation gates remain authoritative.",
    }
