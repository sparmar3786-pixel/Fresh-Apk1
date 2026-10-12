from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean

from backend.quant.option_math import (
    atr,
    bollinger,
    ema,
    macd,
    realized_vol,
    returns_from_prices,
    rolling_zscore,
    rsi,
    sma,
)
from .models import MarketSnapshot, OISignal, OptionPoint, StrategyResult, TradeDecision
from .strategy_ensemble import evaluate_confluence


@dataclass
class IndicatorSet:
    ema_fast: float
    ema_slow: float
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float
    atr14: float
    vwap: float | None
    sma20: float | None
    bb_mid: float | None
    bb_upper: float | None
    bb_lower: float | None
    bb_width: float | None
    zscore20: float | None
    realized_vol20: float | None


def _indicators(snapshot: MarketSnapshot, ema_fast_period: int = 8, ema_slow_period: int = 13) -> IndicatorSet:
    values = snapshot.candles or [snapshot.ltp]
    fast = ema(values, ema_fast_period) or values[-1]
    slow = ema(values, ema_slow_period) or values[-1]
    rsi_value = rsi(values, 14) or 50.0
    macd_value = macd(values, 12, 26, 9) or {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    bb = bollinger(values, 20, 2.0)
    return IndicatorSet(
        ema_fast=fast,
        ema_slow=slow,
        rsi14=rsi_value,
        macd=macd_value["macd"],
        macd_signal=macd_value["signal"],
        macd_hist=macd_value["hist"],
        atr14=atr(values, values, values, 14) or 0.0,
        vwap=snapshot.vwap,
        sma20=sma(values, 20),
        bb_mid=bb["mid"] if bb else None,
        bb_upper=bb["upper"] if bb else None,
        bb_lower=bb["lower"] if bb else None,
        bb_width=bb["width"] if bb else None,
        zscore20=rolling_zscore(values, 20),
        realized_vol20=realized_vol(returns_from_prices(values), 20),
    )


def _advanced_ohlc_indicators(snapshot: MarketSnapshot) -> dict[str, float | str]:
    """Compute extra indicators only from returned OHLC bars; never fabricate missing fields."""
    raw = snapshot.timeframes.get("5m") or snapshot.timeframes.get("1m") or []
    bars: list[tuple[float, float, float]] = []
    for row in raw:
        try:
            high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if min(high, low, close) <= 0 or high < low or close > high or close < low:
            continue
        bars.append((high, low, close))
    result: dict[str, float | str] = {
        "ema50": "N/A", "ema200": "N/A", "stochastic_k14": "N/A",
        "stochastic_d3": "N/A", "williams_r14": "N/A", "roc10_pct": "N/A",
        "adx14": "N/A", "supertrend_direction": "N/A",
        "support20": "N/A", "resistance20": "N/A",
    }
    closes = [bar[2] for bar in bars]
    highs = [bar[0] for bar in bars]
    lows = [bar[1] for bar in bars]
    if len(closes) >= 50:
        result["ema50"] = ema(closes, 50) or "N/A"
    if len(closes) >= 200:
        result["ema200"] = ema(closes, 200) or "N/A"
    if len(closes) >= 11 and closes[-11] > 0:
        result["roc10_pct"] = round((closes[-1] / closes[-11] - 1.0) * 100.0, 4)
    if len(closes) >= 20:
        result["support20"] = min(lows[-20:])
        result["resistance20"] = max(highs[-20:])
    if len(closes) >= 14:
        highest, lowest = max(highs[-14:]), min(lows[-14:])
        span = highest - lowest
        if span > 0:
            result["stochastic_k14"] = round((closes[-1] - lowest) / span * 100.0, 3)
            k_values = []
            for end in range(max(13, len(closes) - 2), len(closes)):
                hi, lo = max(highs[end - 13:end + 1]), min(lows[end - 13:end + 1])
                k_values.append((closes[end] - lo) / (hi - lo) * 100.0 if hi > lo else 50.0)
            result["stochastic_d3"] = round(sum(k_values) / len(k_values), 3)
            result["williams_r14"] = round(-100.0 * (highest - closes[-1]) / span, 3)

    if len(closes) >= 28:
        true_ranges: list[float] = []
        plus_dm: list[float] = []
        minus_dm: list[float] = []
        for i in range(len(closes)):
            previous_close = closes[i - 1] if i else closes[i]
            true_ranges.append(max(
                highs[i] - lows[i],
                abs(highs[i] - previous_close),
                abs(lows[i] - previous_close),
            ))
            if i == 0:
                plus_dm.append(0.0)
                minus_dm.append(0.0)
            else:
                up = highs[i] - highs[i - 1]
                down = lows[i - 1] - lows[i]
                plus_dm.append(up if up > down and up > 0 else 0.0)
                minus_dm.append(down if down > up and down > 0 else 0.0)

        period = 14
        smooth_tr = sum(true_ranges[1:period + 1])
        smooth_plus = sum(plus_dm[1:period + 1])
        smooth_minus = sum(minus_dm[1:period + 1])
        dx_values: list[float] = []
        for i in range(period, len(closes)):
            if i > period:
                smooth_tr = smooth_tr - smooth_tr / period + true_ranges[i]
                smooth_plus = smooth_plus - smooth_plus / period + plus_dm[i]
                smooth_minus = smooth_minus - smooth_minus / period + minus_dm[i]
            if smooth_tr <= 0:
                continue
            plus_di = 100.0 * smooth_plus / smooth_tr
            minus_di = 100.0 * smooth_minus / smooth_tr
            denominator = plus_di + minus_di
            if denominator > 0:
                dx_values.append(100.0 * abs(plus_di - minus_di) / denominator)
        if len(dx_values) >= period:
            adx_value = sum(dx_values[:period]) / period
            for dx in dx_values[period:]:
                adx_value = ((adx_value * (period - 1)) + dx) / period
            result["adx14"] = round(adx_value, 3)

    if len(closes) >= 10:
        period = 10
        true_ranges: list[float] = []
        for i in range(len(closes)):
            previous_close = closes[i - 1] if i else closes[i]
            true_ranges.append(max(
                highs[i] - lows[i],
                abs(highs[i] - previous_close),
                abs(lows[i] - previous_close),
            ))
        atr_values: list[float | None] = [None] * len(closes)
        current_atr = sum(true_ranges[:period]) / period
        atr_values[period - 1] = current_atr
        for i in range(period, len(closes)):
            current_atr = ((current_atr * (period - 1)) + true_ranges[i]) / period
            atr_values[i] = current_atr
        final_upper: float | None = None
        final_lower: float | None = None
        direction = -1
        for i in range(period - 1, len(closes)):
            if atr_values[i] is None:
                continue
            midpoint = (highs[i] + lows[i]) / 2.0
            basic_upper = midpoint + 3.0 * float(atr_values[i])
            basic_lower = midpoint - 3.0 * float(atr_values[i])
            if final_upper is None or closes[i - 1] > final_upper:
                final_upper = basic_upper
            else:
                final_upper = min(final_upper, basic_upper)
            if final_lower is None or closes[i - 1] < final_lower:
                final_lower = basic_lower
            else:
                final_lower = max(final_lower, basic_lower)
            if direction < 0:
                direction = 1 if closes[i] > final_upper else -1
            else:
                direction = -1 if closes[i] < final_lower else 1
        result["supertrend_direction"] = "UP" if direction > 0 else "DOWN"
    return result


def _classify_oi(option: OptionPoint) -> OISignal:
    premium_up = option.premium_change > 0
    oi_up = option.oi_change > 0
    if premium_up and oi_up:
        return OISignal.LONG_BUILDUP
    if not premium_up and oi_up:
        return OISignal.SHORT_BUILDUP
    if premium_up and not oi_up:
        return OISignal.SHORT_COVERING
    if not premium_up and not oi_up:
        return OISignal.LONG_UNWINDING
    return OISignal.NEUTRAL


def _score_options(options: list[OptionPoint], bullish: bool) -> OptionPoint | None:
    target_side = "CE" if bullish else "PE"
    side_options = [o for o in options if o.side == target_side and o.ltp > 0]
    if not side_options:
        return None
    max_oi = max((o.oi for o in side_options), default=1) or 1
    max_volume = max((o.volume for o in side_options), default=1) or 1

    def score(o: OptionPoint) -> float:
        oi = o.oi / max_oi
        volume = o.volume / max_volume
        oi_change = max(0.0, min(1.0, (o.oi_change + 1.0) / 2.0))
        premium_change = max(0.0, min(1.0, (o.premium_change + 1.0) / 2.0))
        greek_quality = 0.0
        if o.delta is not None:
            directional_delta = o.delta if bullish else -o.delta
            greek_quality += max(0.0, min(1.0, directional_delta))
        if o.gamma is not None and o.gamma > 0:
            greek_quality += 0.25
        if o.vega is not None and o.vega > 0:
            greek_quality += 0.15
        return (
            0.32 * oi
            + 0.23 * volume
            + 0.18 * oi_change
            + 0.12 * premium_change
            + 0.15 * min(1.0, greek_quality)
        )

    return max(side_options, key=score)


def analyze(
    snapshot: MarketSnapshot,
    stale_after_seconds: int = 15,
    ema_fast_period: int = 8,
    ema_slow_period: int = 13,
) -> StrategyResult:
    guards: list[str] = []
    values = snapshot.candles or [snapshot.ltp]
    age = max(0.0, (datetime.now(timezone.utc) - snapshot.timestamp).total_seconds())
    if age > stale_after_seconds:
        guards.append("STALE_DATA")
    if len(snapshot.candles) < 20:
        guards.append("INSUFFICIENT_CANDLES")
    if not snapshot.options:
        guards.append("OPTION_CHAIN_MISSING")
    if snapshot.ltp <= 0:
        guards.append("INVALID_LTP")

    ema_fast_period = max(2, min(50, int(ema_fast_period)))
    ema_slow_period = max(3, min(100, int(ema_slow_period)))
    if ema_fast_period >= ema_slow_period:
        ema_fast_period, ema_slow_period = 8, 13

    ind = _indicators(snapshot, ema_fast_period, ema_slow_period)
    bullish = ind.ema_fast > ind.ema_slow and ind.macd_hist >= 0 and ind.rsi14 >= 50
    bearish = ind.ema_fast < ind.ema_slow and ind.macd_hist <= 0 and ind.rsi14 <= 50
    regime = "BULLISH" if bullish and not bearish else "BEARISH" if bearish and not bullish else "MIXED"

    ce = [o for o in snapshot.options if o.side == "CE"]
    pe = [o for o in snapshot.options if o.side == "PE"]
    ce_oi, pe_oi = sum(o.oi for o in ce), sum(o.oi for o in pe)
    pcr = pe_oi / ce_oi if ce_oi else 0.0
    bullish_oi, bearish_oi = sum(o.oi_change for o in ce), sum(o.oi_change for o in pe)
    dominant_oi = "CALL_OI_BUILD" if bullish_oi > bearish_oi else "PUT_OI_BUILD" if bearish_oi > bullish_oi else "BALANCED"

    if bullish and bearish_oi > bullish_oi * 1.25:
        bullish, regime = False, "BULLISH_WITH_BEARISH_OI_OVERRIDE"
    if bearish and bullish_oi > bearish_oi * 1.25:
        bearish, regime = False, "BEARISH_WITH_BULLISH_OI_OVERRIDE"

    chosen = None if "STALE_DATA" in guards else (
        _score_options(snapshot.options, True) if bullish else
        _score_options(snapshot.options, False) if bearish else None
    )

    if chosen:
        atr_value = ind.atr14 or chosen.ltp * 0.03
        entry = chosen.ltp
        stop = max(0.05, entry - atr_value)
        target = entry + atr_value * 1.8

        confidence = 55.0
        if (bullish and ind.ema_fast > ind.ema_slow) or (bearish and ind.ema_fast < ind.ema_slow):
            confidence += 7
        if (bullish and ind.macd_hist > 0) or (bearish and ind.macd_hist < 0):
            confidence += 7
        if ind.rsi14 > 55 or ind.rsi14 < 45:
            confidence += 6
        if ind.zscore20 is not None and abs(ind.zscore20) < 2.5:
            confidence += 4
        if chosen.oi_change != 0:
            confidence += 7
        if chosen.premium_change != 0:
            confidence += 5
        if chosen.delta is not None and ((bullish and chosen.delta > 0) or (bearish and chosen.delta < 0)):
            confidence += 5

        decision = TradeDecision.CALL_BUY if bullish else TradeDecision.PUT_BUY
        reasons = [
            f"Regime={regime}",
            f"EMA{ema_fast_period}={ind.ema_fast:.2f} vs EMA{ema_slow_period}={ind.ema_slow:.2f}",
            f"RSI14={ind.rsi14:.1f}, MACD={ind.macd:.3f}, histogram={ind.macd_hist:.3f}",
            f"PCR={pcr:.2f}, {dominant_oi}",
            f"Quant: BB width={ind.bb_width if ind.bb_width is not None else 0.0:.4f} z20={ind.zscore20 if ind.zscore20 is not None else 0.0:.2f}",
            f"Strike {chosen.strike:.0f} {chosen.side} selected by OI/liquidity + quant Greek quality",
        ]
        if chosen.iv is not None:
            reasons.append(f"IV={chosen.iv:.2f}")
        if chosen.delta is not None or chosen.gamma is not None:
            reasons.append(
                f"Greeks: Δ={chosen.delta if chosen.delta is not None else 0:.3f}, "
                f"Γ={chosen.gamma if chosen.gamma is not None else 0:.4f}, "
                f"Vega={chosen.vega if chosen.vega is not None else 0:.3f}"
            )
    else:
        decision = TradeDecision.WAIT if not guards else TradeDecision.NO_TRADE
        confidence = 35.0 if decision == TradeDecision.WAIT else 15.0
        entry = stop = target = None
        reasons = [
            f"Regime={regime}",
            f"PCR={pcr:.2f}, {dominant_oi}",
            "Directional + quant components are not sufficiently aligned for a clean entry.",
        ]
        chosen = None

    confluence = evaluate_confluence(
        snapshot,
        decision.value,
        indicators={
            "ema_fast": ind.ema_fast,
            "ema_slow": ind.ema_slow,
            "macd_hist": ind.macd_hist,
            "rsi14": ind.rsi14,
        },
        selected_option=chosen,
    )
    timeframe_state = confluence["checks"].get("multi_timeframe")
    if chosen and timeframe_state == "ALIGNED":
        confidence = min(99.0, confidence + 3.0)
        reasons.append("Confluence: multi-timeframe direction agrees with the candidate.")
    elif chosen and timeframe_state == "CONFLICT":
        confidence = max(0.0, confidence - 6.0)
        reasons.append("Confluence warning: timeframes conflict; confidence reduced.")
    if confluence.get("confluence_score") is not None:
        reasons.append(
            f"Confluence evidence score={confluence['confluence_score']:.1f}/100 "
            "(alignment score, not probability of profit)."
        )

    return StrategyResult(
        index=snapshot.index,
        decision=decision,
        confidence=min(99.0, confidence),
        regime=regime,
        strike=chosen.strike if chosen else None,
        option_side=chosen.side if chosen else None,
        entry=entry,
        stop_loss=stop,
        target=target,
        reason=reasons,
        guards=guards,
        oi_summary={
            "call_oi": ce_oi,
            "put_oi": pe_oi,
            "call_oi_change": bullish_oi,
            "put_oi_change": bearish_oi,
            "pcr": pcr,
            "classification": dominant_oi,
            "selected_oi_regime": _classify_oi(chosen).value if chosen else OISignal.NEUTRAL.value,
        },
        indicators={
            "ema8": ind.ema_fast if ema_fast_period == 8 else ind.ema_fast,
            "ema13": ind.ema_slow if ema_slow_period == 13 else ind.ema_slow,
            "ema_fast": ind.ema_fast,
            "ema_slow": ind.ema_slow,
            "ema_fast_period": ema_fast_period,
            "ema_slow_period": ema_slow_period,
            "sma20": ind.sma20 if ind.sma20 is not None else 0.0,
            "bb_mid": ind.bb_mid if ind.bb_mid is not None else 0.0,
            "bb_upper": ind.bb_upper if ind.bb_upper is not None else 0.0,
            "bb_lower": ind.bb_lower if ind.bb_lower is not None else 0.0,
            "bb_width": ind.bb_width if ind.bb_width is not None else 0.0,
            "rsi14": ind.rsi14,
            "macd": ind.macd,
            "macd_signal": ind.macd_signal,
            "macd_hist": ind.macd_hist,
            "atr14": ind.atr14,
            "vwap": ind.vwap if ind.vwap is not None else 0.0,
            "zscore20": ind.zscore20 if ind.zscore20 is not None else 0.0,
            "realized_vol20": ind.realized_vol20 if ind.realized_vol20 is not None else 0.0,
            **_advanced_ohlc_indicators(snapshot),
        },
        timeframe_analysis={
            "entry_timeframe": "1m",
            "setup_timeframe": "5m",
            "regime_timeframe": "15m",
            **confluence,
        },
    )


def build_qualified_trade_plans(results: list[StrategyResult], limit: int = 5) -> list[dict]:
    plans: list[dict] = []
    for result in results:
        if (
            result.decision not in {TradeDecision.CALL_BUY, TradeDecision.PUT_BUY}
            or result.guards
        ):
            continue
        if result.trade_plan is not None and result.trade_plan.get("eligible"):
            plan = dict(result.trade_plan)
        elif result.entry is not None and result.stop_loss is not None and result.target is not None:
            # Backward-compatible representation for deterministic strategy
            # callers/tests that do not run the multi-timeframe trade desk.
            plan = result.model_dump(mode="json")
        else:
            continue
        plan.update({
            "decision": result.decision.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "guards": result.guards,
            "timeframe_analysis": result.timeframe_analysis,
            "regime": result.regime,
        })
        plans.append(plan)
    plans.sort(key=lambda item: float(item.get("confidence", 0)), reverse=True)
    return plans[: max(0, limit)]
