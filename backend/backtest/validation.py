"""Backtest readiness and paper-trading validation gates.

All returns are expressed in R-multiples. Cost/slippage inputs must also be
expressed in R-multiples so no currency assumptions are silently invented.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from backend.backtest.engine import Backtester, compute_metrics

MIN_VERIFIED_TRADES = 100
MIN_VERIFIED_WIN_RATE = 0.80


def net_of_costs(
    trades: Iterable[dict[str, Any]],
    *,
    slippage_r: float = 0.0,
    transaction_cost_r: float = 0.0,
) -> list[dict[str, Any]]:
    if slippage_r < 0 or transaction_cost_r < 0:
        raise ValueError("slippage_r and transaction_cost_r must be non-negative")
    deduction = float(slippage_r) + float(transaction_cost_r)
    result = []
    for trade in trades:
        gross_r = float(trade.get("r", 0.0) or 0.0)
        result.append({**trade, "gross_r": gross_r, "r": gross_r - deduction})
    return result


def walk_forward_report(
    trades: Iterable[dict[str, Any]],
    *,
    folds: int = 5,
    slippage_r: float = 0.02,
    transaction_cost_r: float = 0.02,
) -> dict[str, Any]:
    rows = list(trades)
    # Chronology must be explicit. Unparseable timestamps sort last and are
    # flagged, rather than silently pretending the sample is time ordered.
    missing_timestamps = sum(not row.get("timestamp") for row in rows)
    def sort_key(row: dict[str, Any]):
        raw = row.get("timestamp")
        if not raw:
            return (1, "")
        try:
            return (0, datetime.fromisoformat(str(raw).replace("Z", "+00:00")).isoformat())
        except ValueError:
            return (1, "")
    ordered = sorted(rows, key=sort_key)
    net = net_of_costs(ordered, slippage_r=slippage_r, transaction_cost_r=transaction_cost_r)
    backtester = Backtester(net)
    wf = backtester.walk_forward(folds)
    return {
        "sample_size": len(net),
        "chronological": missing_timestamps == 0,
        "missing_timestamps": missing_timestamps,
        "cost_assumptions_r_per_trade": {
            "slippage": slippage_r,
            "transaction_cost": transaction_cost_r,
        },
        "gross_metrics": compute_metrics(ordered),
        "net_metrics": compute_metrics(net),
        "walk_forward": wf,
        "out_of_sample": backtester.out_of_sample(0.7),
        "regime_wise_net": backtester.regime_wise(),
        "robustness": backtester.robustness(),
        "readiness": "INSUFFICIENT_DATA" if len(net) < MIN_VERIFIED_TRADES else "REVIEW_REQUIRED",
        "note": "R-multiple costs are explicit assumptions; replace with measured broker fees and slippage before relying on results.",
    }


def evaluate_readiness(
    trades: Iterable[dict[str, Any]],
    *,
    slippage_r: float = 0.02,
    transaction_cost_r: float = 0.02,
    min_trades: int = MIN_VERIFIED_TRADES,
    min_win_rate: float = MIN_VERIFIED_WIN_RATE,
) -> dict[str, Any]:
    rows = list(trades)
    net = net_of_costs(rows, slippage_r=slippage_r, transaction_cost_r=transaction_cost_r)
    metrics = compute_metrics(net)
    enough = metrics["n"] >= min_trades
    win_rate_pass = metrics["win_rate"] is not None and metrics["win_rate"] >= min_win_rate
    expectancy_pass = metrics["expectancy"] is not None and metrics["expectancy"] > 0
    passed = enough and win_rate_pass and expectancy_pass
    return {
        "passed": passed,
        "live_execution_allowed": False,
        "paper_only": True,
        "checks": {
            "minimum_trade_count": {"passed": enough, "actual": metrics["n"], "required": min_trades},
            "net_win_rate": {"passed": win_rate_pass, "actual": metrics["win_rate"], "required": min_win_rate},
            "net_expectancy": {"passed": expectancy_pass, "actual": metrics["expectancy"], "required": "> 0"},
        },
        "net_metrics": metrics,
        "reason": "All checks passed; still requires separate human approval and a dedicated live-execution implementation." if passed else "Readiness checks failed; continue paper trading. No live order placement is enabled by this module.",
    }
