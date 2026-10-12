"""Historical candle replay for a deterministic EMA/ATR baseline.

This is explicitly an index-spot proxy. It does not pretend to backtest option-premium
fills, historical Greeks, or a strike that was not historically selected.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _ema(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if period < 2 or len(values) < period:
        return output
    seed = sum(values[:period]) / period
    output[period - 1] = seed
    alpha = 2.0 / (period + 1)
    current = seed
    for i in range(period, len(values)):
        current = alpha * values[i] + (1.0 - alpha) * current
        output[i] = current
    return output


def _atr(candles: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    trs: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high, low, close = candle["high"], candle["low"], candle["close"]
        tr = high - low if previous_close is None else max(
            high - low, abs(high - previous_close), abs(low - previous_close)
        )
        trs.append(max(0.0, tr))
        previous_close = close
    result: list[float | None] = [None] * len(trs)
    if len(trs) < period:
        return result
    current = sum(trs[:period]) / period
    result[period - 1] = current
    for i in range(period, len(trs)):
        current = ((current * (period - 1)) + trs[i]) / period
        result[i] = current
    return result


def normalize_candles(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Validate and de-duplicate SmartAPI [timestamp, open, high, low, close, volume] rows."""
    by_timestamp: dict[float, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        try:
            stamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            values = [_finite(row[i]) for i in range(1, 6)]
        except (TypeError, ValueError):
            continue
        if any(v is None for v in values):
            continue
        open_price, high, low, close, volume = (float(v) for v in values)
        if min(open_price, high, low, close) <= 0 or volume < 0 or high < low:
            continue
        if high < max(open_price, close) or low > min(open_price, close):
            continue
        by_timestamp[stamp.timestamp()] = {
            "timestamp": stamp.isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    return [by_timestamp[key] for key in sorted(by_timestamp)]


def run_ema_atr_backtest(
    rows: list[list[Any]],
    *,
    fast_period: int = 8,
    slow_period: int = 13,
    atr_period: int = 14,
    stop_atr: float = 1.5,
    target_r: float = 2.0,
    max_hold_bars: int = 30,
    slippage_r: float = 0.02,
    transaction_cost_r: float = 0.02,
) -> dict[str, Any]:
    if fast_period < 2 or slow_period <= fast_period or slow_period > 100:
        raise ValueError("EMA periods must satisfy 2 <= fast < slow <= 100")
    if atr_period < 2 or not 0.25 <= stop_atr <= 10:
        raise ValueError("ATR period or stop multiplier is outside allowed bounds")
    if not 0.5 <= target_r <= 10 or not 1 <= max_hold_bars <= 500:
        raise ValueError("Target R or max hold bars is outside allowed bounds")
    if slippage_r < 0 or transaction_cost_r < 0:
        raise ValueError("cost assumptions cannot be negative")

    candles = normalize_candles(rows)
    minimum = max(slow_period + 2, atr_period + 2)
    if len(candles) < minimum:
        return {
            "ok": False,
            "status": "INSUFFICIENT_HISTORY",
            "candle_count": len(candles),
            "minimum_candles": minimum,
            "trades": [],
            "metrics": {"n": 0, "win_rate": None, "expectancy_r": None},
            "note": "Not enough valid historical candles; no backtest result was inferred.",
        }

    closes = [c["close"] for c in candles]
    fast = _ema(closes, fast_period)
    slow = _ema(closes, slow_period)
    atr = _atr(candles, atr_period)
    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None

    def close_trade(exit_index: int, exit_price: float, reason: str) -> None:
        nonlocal position
        assert position is not None
        direction = position["direction"]
        risk = position["risk"]
        gross_r = ((exit_price - position["entry_price"]) / risk) * direction
        net_r = gross_r - slippage_r - transaction_cost_r
        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": candles[exit_index]["timestamp"],
            "side": "CE" if direction > 0 else "PE",
            "direction": "LONG_SPOT" if direction > 0 else "SHORT_SPOT",
            "entry_price": round(position["entry_price"], 4),
            "exit_price": round(exit_price, 4),
            "stop_loss": round(position["stop"], 4),
            "target": round(position["target"], 4),
            "bars_held": exit_index - position["entry_index"],
            "exit_reason": reason,
            "gross_r": round(gross_r, 4),
            "slippage_r": slippage_r,
            "transaction_cost_r": transaction_cost_r,
            "r": round(net_r, 4),
        })
        position = None

    for i in range(1, len(candles)):
        if fast[i] is None or slow[i] is None or fast[i - 1] is None or slow[i - 1] is None:
            continue
        candle = candles[i]
        if position is not None:
            direction = position["direction"]
            # Conservative bar replay: if stop and target both touched in one
            # candle, assume the stop was hit first (no optimistic ordering).
            stop_hit = candle["low"] <= position["stop"] if direction > 0 else candle["high"] >= position["stop"]
            target_hit = candle["high"] >= position["target"] if direction > 0 else candle["low"] <= position["target"]
            if stop_hit:
                close_trade(i, position["stop"], "STOP_LOSS")
                continue
            if target_hit:
                close_trade(i, position["target"], "TARGET")
                continue
            crossed_against = (
                direction > 0 and fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
            ) or (
                direction < 0 and fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
            )
            if crossed_against:
                close_trade(i, candle["close"], "EMA_REVERSAL")
                continue
            if i - position["entry_index"] >= max_hold_bars:
                close_trade(i, candle["close"], "TIME_EXIT")
                continue

        if position is None and atr[i] is not None and atr[i] > 0 and i + 1 < len(candles):
            bullish_cross = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
            bearish_cross = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
            if bullish_cross or bearish_cross:
                # Signal is known only after candle i closes. Fill at the next
                # candle's open, never at the same close that created the signal.
                next_candle = candles[i + 1]
                direction = 1 if bullish_cross else -1
                entry = next_candle["open"]
                risk = float(atr[i]) * stop_atr
                position = {
                    "direction": direction,
                    "entry_index": i + 1,
                    "entry_time": next_candle["timestamp"],
                    "entry_price": entry,
                    "risk": risk,
                    "stop": entry - direction * risk,
                    "target": entry + direction * risk * target_r,
                }

    if position is not None:
        close_trade(len(candles) - 1, candles[-1]["close"], "END_OF_SAMPLE")

    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = peak = max_drawdown = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    metrics = {
        "n": len(trades),
        "win_rate": round(len(wins) / len(trades), 4) if trades else None,
        "expectancy_r": round(sum(rs) / len(rs), 4) if trades else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "UNBOUNDED"),
        "net_total_r": round(sum(rs), 4),
        "max_drawdown_r": round(max_drawdown, 4),
        "average_win_r": round(sum(wins) / len(wins), 4) if wins else None,
        "average_loss_r": round(sum(losses) / len(losses), 4) if losses else None,
    }
    return {
        "ok": True,
        "status": "COMPLETED" if trades else "NO_SIGNALS",
        "mode": "INDEX_SPOT_PROXY",
        "candle_count": len(candles),
        "first_candle": candles[0]["timestamp"],
        "last_candle": candles[-1]["timestamp"],
        "parameters": {
            "fast_ema": fast_period,
            "slow_ema": slow_period,
            "atr_period": atr_period,
            "stop_atr": stop_atr,
            "target_r": target_r,
            "max_hold_bars": max_hold_bars,
            "slippage_r": slippage_r,
            "transaction_cost_r": transaction_cost_r,
        },
        "metrics": metrics,
        "trades": trades,
        "assumptions": [
            "Underlying index candles only; results are not option-premium P&L.",
            "Signal is computed from a completed candle and entry is filled at the next candle open.",
            "If stop and target both touch in one candle, stop loss is assumed first.",
            "Costs are explicit R-multiple deductions, not rupee brokerage estimates.",
            "Past results do not predict future returns.",
        ],
    }
