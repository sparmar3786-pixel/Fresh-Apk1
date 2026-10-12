"""Original agent-style research layer for Fresh Algo Signal.

Research patterns are informed by public trading projects, but this module is
an original, dependency-free implementation. It does not bundle their source
code or models. Specialist reports are evidence diagnostics, not independent
model predictions; deterministic data-quality and risk gates remain authoritative.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from typing import Any


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _direction(decision: Any) -> str:
    value = str(getattr(decision, "value", decision) or "").upper()
    if value == "CALL BUY":
        return "BULLISH"
    if value == "PUT BUY":
        return "BEARISH"
    if value in {"WAIT", "NO TRADE"}:
        return value
    return "UNKNOWN"


_POSITIVE_TERMS = re.compile(r"\b(beat|beats|upgrade|upgraded|growth|surge|surges|rally|bullish|record high|inflow|strong demand|profit rises)\b", re.I)
_NEGATIVE_TERMS = re.compile(r"\b(miss|misses|downgrade|downgraded|decline|falls|selloff|bearish|outflow|weak demand|loss widens|fraud|default)\b", re.I)


def _sentiment_evidence_report(evidence: list[Any]) -> dict[str, Any]:
    """Measure evidence coverage and a deliberately simple headline polarity hint.

    The lexical hint is not a financial sentiment model and never votes on a
    trade direction. It is surfaced for the LLM to challenge alongside source
    text, dates and provenance. Missing dates are not treated as fresh.
    """
    providers: set[str] = set()
    domains: set[str] = set()
    dated = 0
    positive_hits = 0
    negative_hits = 0
    usable = 0
    for item in evidence:
        provider = str(_get(item, "provider", "") or "").strip().lower()
        if provider:
            providers.add(provider)
        url = str(_get(item, "url", "") or "").strip()
        try:
            host = urlsplit(url).hostname
            if host:
                domains.add(host.lower().removeprefix("www."))
        except ValueError:
            pass
        if str(_get(item, "published_at", "") or "").strip():
            dated += 1
        text = " ".join((
            str(_get(item, "title", "") or ""),
            str(_get(item, "snippet", "") or ""),
        ))[:1500]
        pos = len(_POSITIVE_TERMS.findall(text))
        neg = len(_NEGATIVE_TERMS.findall(text))
        positive_hits += pos
        negative_hits += neg
        if text.strip():
            usable += 1
    if not evidence:
        status, polarity = "UNAVAILABLE", "UNKNOWN"
    elif not usable:
        status, polarity = "LOW_QUALITY", "UNKNOWN"
    elif positive_hits > negative_hits:
        status, polarity = "PARTIAL", "POSITIVE_LEXICAL_HINT"
    elif negative_hits > positive_hits:
        status, polarity = "PARTIAL", "NEGATIVE_LEXICAL_HINT"
    else:
        status, polarity = "PARTIAL", "MIXED_OR_NEUTRAL"
    return {
        "status": status,
        "evidence_count": len(evidence),
        "usable_text_count": usable,
        "provider_count": len(providers),
        "providers": sorted(providers),
        "unique_domain_count": len(domains),
        "dated_evidence_count": dated,
        "undated_evidence_count": max(0, len(evidence) - dated),
        "lexical_polarity_hint": polarity,
        "positive_term_hits": positive_hits,
        "negative_term_hits": negative_hits,
        "warning": "Lexical hint only; not a trained sentiment model, not freshness validation, and never a standalone trade trigger.",
    }


def build_agent_ensemble(
    snapshot: Any,
    strategy: Any,
    market_brief: dict[str, Any] | None = None,
    evidence: list[Any] | None = None,
) -> dict[str, Any]:
    """Create auditable specialist reports from already supplied market data.

    Sentiment, portfolio and reflection roles explicitly report unavailable when
    their source data are absent; this function never invents news or trade history.
    """
    brief = market_brief or {}
    evidence = evidence or []
    candidate = _direction(_get(strategy, "decision"))
    guards = [str(x) for x in (_get(strategy, "guards", []) or [])]
    indicators = _get(strategy, "indicators", {}) or {}
    regime = str(_get(strategy, "regime", "UNKNOWN") or "UNKNOWN").upper()

    ema_fast = _number(indicators.get("ema_fast"))
    ema_slow = _number(indicators.get("ema_slow"))
    macd_hist = _number(indicators.get("macd_hist"))
    rsi = _number(indicators.get("rsi14"))
    technical_votes: list[str] = []
    if ema_fast is not None and ema_slow is not None:
        technical_votes.append("BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "NEUTRAL")
    if macd_hist is not None:
        technical_votes.append("BULLISH" if macd_hist > 0 else "BEARISH" if macd_hist < 0 else "NEUTRAL")
    technical = "UNKNOWN" if not technical_votes else (
        technical_votes[0] if all(v == technical_votes[0] for v in technical_votes)
        else "CONFLICT"
    )

    options = list(_get(snapshot, "options", []) or []) if snapshot is not None else []
    flow = {"LONG_BUILDUP": 0, "SHORT_BUILDUP": 0, "SHORT_COVERING": 0, "LONG_UNWINDING": 0}
    call_pressure = 0
    put_pressure = 0
    for option in options:
        oi_change = _number(_get(option, "oi_change"))
        premium_change = _number(_get(option, "premium_change"))
        side = str(_get(option, "side", "") or "").upper()
        if side not in {"CE", "PE"} or oi_change is None or premium_change is None:
            continue
        if premium_change > 0 and oi_change > 0:
            category, signed = "LONG_BUILDUP", 1
        elif premium_change < 0 and oi_change > 0:
            category, signed = "SHORT_BUILDUP", -1
        elif premium_change > 0 and oi_change < 0:
            category, signed = "SHORT_COVERING", 1
        elif premium_change < 0 and oi_change < 0:
            category, signed = "LONG_UNWINDING", -1
        else:
            continue
        flow[category] += 1
        if side == "CE":
            call_pressure += signed
        else:
            put_pressure += signed
    flow_direction = "UNKNOWN" if not any(flow.values()) else (
        "BULLISH" if call_pressure > put_pressure else
        "BEARISH" if put_pressure > call_pressure else "BALANCED"
    )

    sentiment_report = _sentiment_evidence_report(evidence)
    adaptive_guard = brief.get("hard_guards") or []
    agent_reports = {
        "market_analyst": {
            "status": "AVAILABLE" if regime != "UNKNOWN" else "PARTIAL",
            "regime": regime,
            "direction": candidate if candidate in {"BULLISH", "BEARISH"} else "UNKNOWN",
        },
        "quant_analyst": {
            "status": "AVAILABLE" if technical != "UNKNOWN" else "DATA_GAP",
            "direction": technical,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "macd_hist": macd_hist,
            "rsi14": rsi,
            "note": "Deterministic indicators only; no trained ML model is claimed.",
        },
        "options_flow_analyst": {
            "status": "AVAILABLE" if any(flow.values()) else "DATA_GAP",
            "direction": flow_direction,
            "classification_counts": flow,
            "note": "Premium/OI sign classification is heuristic and requires full-chain context.",
        },
        "sentiment_analyst": {
            **sentiment_report,
            "note": "Evidence-quality and lexical diagnostics only; the LLM must inspect source text and cannot override market-data or risk guards.",
        },
        "risk_auditor": {
            "status": "BLOCKED" if guards or adaptive_guard else "CHECKED",
            "blocks": sorted(set(guards + [str(x) for x in adaptive_guard])),
            "entry": _get(strategy, "entry"),
            "stop_loss": _get(strategy, "stop_loss"),
            "target": _get(strategy, "target"),
            "note": "Existing deterministic freshness and risk gates remain authoritative.",
        },
        "reflection_analyst": {
            "status": "UNAVAILABLE",
            "note": "Closed-trade outcome history is not passed into this live analysis; no learning claim is made.",
        },
        "portfolio_manager": {
            "status": "UNAVAILABLE",
            "note": "Account equity, current exposure and portfolio limits are not present in the analysis packet.",
        },
    }

    directions = [
        report.get("direction")
        for name, report in agent_reports.items()
        if name in {"market_analyst", "quant_analyst", "options_flow_analyst"}
        and report.get("direction") in {"BULLISH", "BEARISH"}
    ]
    conflict = len(set(directions)) > 1
    hard_block = bool(guards or adaptive_guard)
    return {
        "version": "fresh-agent-ensemble-v1.1",
        "candidate": candidate,
        "consensus": "NO TRADE" if hard_block else "CONFLICT" if conflict else (
            directions[0] if directions and all(v == directions[0] for v in directions) else "INSUFFICIENT_EVIDENCE"
        ),
        "hard_block": hard_block,
        "agents": agent_reports,
        "safety_note": "Agent reports are diagnostics, not independent model predictions. Missing news, portfolio or outcome data remain unavailable; no order is placed.",
    }
