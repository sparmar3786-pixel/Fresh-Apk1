from __future__ import annotations

from backend.app.models import TradeDecision
from backend.pipeline.base import PartResult, register
from backend.pipeline.context import PipelineContext
from backend.pipeline.decision import PipelineDecision
from backend.pipeline.part25_risk_engine import TUNING
from backend.pipeline.trade_management import build_option_levels, size_in_lots, strike_quality


def _step(ctx: PipelineContext) -> float:
    ks = sorted(s["strike"] for s in (ctx.get("frame") or []))
    diffs = [b - a for a, b in zip(ks, ks[1:]) if b > a]
    return min(diffs) if diffs else 50.0


def _plan(ctx: PipelineContext, side: str, strike: float, strategy_ids: list[str]):
    row = next((s for s in (ctx.get("frame") or []) if s["strike"] == strike), None)
    if row is None:
        return None, "missing_strike"
    key = "ce" if side == "CE" else "pe"
    entry_ltp = row.get(f"{key}_ltp")
    if entry_ltp is None or entry_ltp <= 0:
        return None, "missing_premium"
    liquidity = ctx.get("liquidity") or {}
    if liquidity.get("low_liquidity"):
        return None, "low_liquidity"

    risk = ctx.get("risk") or {}
    min_rr = float(risk.get("min_rr", 1.8))
    levels = build_option_levels(
        ltp=entry_ltp,
        bid=row.get(f"{key}_bid"),
        ask=row.get(f"{key}_ask"),
        stop_pct=float(risk.get("premium_sl_pct", TUNING["premium_sl_pct"])),
        min_rr=min_rr,
        tick_size=0.05,
    )
    if not levels.get("ok"):
        return None, str(levels.get("reason", "invalid_levels"))

    lot_sizes = ctx.get("verified_lot_sizes") or {}
    sizing = size_in_lots(
        capital_inr=ctx.get("account_capital_inr"),
        risk_fraction=float(ctx.get("risk_fraction", 0.01)),
        entry=levels["entry"],
        stop_loss=levels["stop_loss"],
        lot_size=lot_sizes.get(ctx.index),
    )
    _, strike_meta = strike_quality(row, side, float(ctx.get("atm_strike") or strike), _step(ctx))
    return {
        "plan_id": f"{ctx.index}-{side}-{strike:g}",
        "index": ctx.index,
        "side": side,
        "strike": strike,
        "entry": levels["entry"],
        "entry_basis": levels["entry_basis"],
        "execution_ready": levels["execution_ready"],
        "bid": levels["bid"],
        "ask": levels["ask"],
        "spread_pct": levels["spread_pct"],
        "stop_loss": levels["stop_loss"],
        "risk_per_unit": levels["risk_per_unit"],
        "target": levels["target1"],
        "target1": levels["target1"],
        "target2": levels["target2"],
        "rr": levels["rr_target1"],
        "trail_after_target1": levels["trail_after_target1"],
        "time_exit_required": levels["time_exit_required"],
        "position_size": sizing["quantity"],
        "position_size_status": sizing["status"],
        "estimated_max_loss_inr": sizing.get("estimated_max_loss_inr"),
        "lots": sizing.get("lots"),
        "strike_quality": strike_meta,
        "confidence": ctx.get("confidence", 0.0),
        "strategy_ids": strategy_ids,
        "regime": ctx.get("regime"),
        "advisory_only": True,
        "live_order_placement": False,
    }, "ok"


@register(32)
async def run(ctx: PipelineContext) -> PartResult:
    dq = ctx.get("dq")
    override = ctx.get("override") or {}
    oi = ctx.get("oi") or {}
    ai = ctx.get("ai") or {}
    conflict = ctx.get("conflict") or {}
    decision = PipelineDecision(index=ctx.index, regime=ctx.get("regime"), confidence=ctx.get("confidence", 0.0))
    if dq is not None and not getattr(dq, "passed", True):
        decision.verdict = TradeDecision.WAIT
        decision.notes.append("DATA_QUALITY_FAIL -> NO SIGNAL")
        ctx.put("decision", decision)
        return PartResult(32, "Final Decision", data_gap=True, output={"verdict": decision.verdict.value})
    adaptive = ctx.get("adaptive") or {}
    adaptive_vote = adaptive.get("decision_vote") or {}
    hard_guards = adaptive.get("hard_guards") or []
    adaptive_guard = adaptive_vote.get("guard")
    if hard_guards or adaptive_guard:
        decision.verdict = TradeDecision.WAIT
        decision.notes.append("ADAPTIVE_SAFETY_GUARD -> NO SIGNAL")
        decision.suppression_reasons.extend(hard_guards)
        if adaptive_guard and adaptive_guard not in decision.suppression_reasons:
            decision.suppression_reasons.append(adaptive_guard)
        ctx.put("decision", decision)
        return PartResult(32, "Final Decision", data_gap=True, output={
            "verdict": decision.verdict.value,
            "safety_guards": decision.suppression_reasons,
        })
    action = override.get("action", "NONE")
    decision.override = action
    decision.override_reason = override.get("reason", "")
    net = float(oi.get("bias", 0.0)) + float((ctx.get("ce_engine") or {}).get("score", 0.0)) * 0.5 + float((ctx.get("pe_engine") or {}).get("score", 0.0)) * 0.5
    side = "CE" if net >= 0 else "PE"
    confidence = float(ctx.get("confidence", 0.0))
    decision.confidence = confidence
    scan = [r for r in ctx.ensure_strategy_scan() if r.get("fired") and r.get("side") == side]
    if action in {"BLOCK", "EXIT"} or conflict.get("conflict"):
        decision.verdict = TradeDecision.WAIT
        decision.notes.append("blocked: opposite-side/strategy conflict")
        ctx.put("decision", decision)
        return PartResult(32, "Final Decision", output={"verdict": decision.verdict.value})
    if abs(net) < 0.05 or confidence < TUNING["min_confidence"]:
        decision.verdict = TradeDecision.WAIT
        decision.notes.append("directional evidence or confidence too weak")
        ctx.put("decision", decision)
        return PartResult(32, "Final Decision", output={"verdict": decision.verdict.value})

    atm = ctx.get("atm_strike")
    step = _step(ctx)
    rows = ctx.get("frame") or []
    ranked = []
    if atm is not None:
        for row in rows:
            strike = row.get("strike")
            if strike is None or abs(float(strike) - float(atm)) > 3 * step:
                continue
            score, meta = strike_quality(row, side, float(atm), step)
            if meta.get("eligible"):
                ranked.append((score, float(strike)))
    ranked.sort(key=lambda item: item[0])
    candidates = []
    for _, strike in ranked[:5]:
        plan, reason = _plan(ctx, side, strike, [r.get("strategy_id") for r in scan[:6]])
        if plan:
            candidates.append(plan)
        else:
            decision.suppression_reasons.append(f"{side} {strike:g}: {reason}")
    decision.plans = candidates
    decision.plans_qualifying = len(candidates)
    decision.plans_suppressed = len(decision.suppression_reasons)
    if ai.get("wait_override"):
        decision.verdict = TradeDecision.WAIT
        decision.notes.append("AI final WAIT override")
    elif candidates:
        decision.verdict = TradeDecision.CALL_BUY if side == "CE" else TradeDecision.PUT_BUY
        if any(not plan["execution_ready"] for plan in candidates):
            decision.notes.append("Indicative LTP plans only: live bid/ask quote missing; do not treat as executable entries")
        if any(plan["position_size_status"] != "sized" for plan in candidates):
            decision.notes.append("Position size withheld until account capital and current verified lot size are configured")
    else:
        decision.verdict = TradeDecision.NO_TRADE
        decision.notes.append("directional setup found but no plan passed risk/liquidity gates")
    ctx.put("decision", decision)
    return PartResult(32, "Final Decision", output={
        "verdict": decision.verdict.value,
        "plans": decision.plans_qualifying,
        "suppressed": decision.plans_suppressed,
    })
