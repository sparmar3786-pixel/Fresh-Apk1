"""Deterministic backtest, walk-forward, Monte-Carlo, robustness and drift tooling."""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional


def _streak(trades: List[dict]) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for t in trades:
        if float(t.get("r", 0) or 0) > 0:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def _max_drawdown(rs: List[float]) -> float:
    peak = cum = mdd = 0.0
    for r in rs:
        cum += r; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    return abs(mdd)


def compute_metrics(trades: List[dict]) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": None, "loss_rate": None, "average_r": None, "expectancy": None, "profit_factor": None, "max_drawdown": None, "max_consecutive_wins": 0, "max_consecutive_losses": 0, "time_of_day": {}}
    rs = [float(t.get("r", 0.0) or 0.0) for t in trades]
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    gross_profit = sum(wins); gross_loss = abs(sum(losses))
    tod: Dict[str, List[float]] = {}
    for t in trades:
        bucket = str(t.get("time", ""))[:2] + ":00" if t.get("time") else "na"
        tod.setdefault(bucket, []).append(float(t.get("r", 0.0) or 0.0))
    best_w, best_l = _streak(trades)
    avg = sum(rs) / n
    return {"n": n, "win_rate": round(len(wins)/n, 4), "loss_rate": round(len(losses)/n, 4), "average_r": round(avg, 4), "expectancy": round(avg, 4), "profit_factor": round(gross_profit/gross_loss, 4) if gross_loss > 0 else (float("inf") if gross_profit > 0 else None), "max_drawdown": round(_max_drawdown(rs), 4), "max_consecutive_wins": best_w, "max_consecutive_losses": best_l, "time_of_day": {k: round(sum(v)/len(v), 4) for k, v in sorted(tod.items())}}


def _group_by(trades: List[dict], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[dict]] = {}
    for t in trades: groups.setdefault(str(t.get(key, "na")), []).append(t)
    return {k: compute_metrics(v) for k, v in groups.items()}


class Backtester:
    def __init__(self, trades: Optional[List[dict]] = None) -> None:
        self.trades = list(trades or [])
    def overall(self): return compute_metrics(self.trades)
    def strategy_wise(self): return _group_by(self.trades, "strategy_id")
    def index_wise(self): return _group_by(self.trades, "index")
    def ce_vs_pe(self): return _group_by(self.trades, "side")
    def expiry_vs_non_expiry(self): return _group_by([{**t, "expiry_flag": "expiry" if t.get("is_expiry") else "non_expiry"} for t in self.trades], "expiry_flag")
    def time_window(self): return _group_by([{**t, "window": str(t.get("time", ""))[:2] + ":00" if t.get("time") else "na"} for t in self.trades], "window")
    def strike_distance(self):
        def bucket(d):
            d = abs(float(d or 0)); return "ATM" if d <= 0 else ("1-2" if d <= 2 else ("3-5" if d <= 5 else ">5"))
        return _group_by([{**t, "dist_bucket": bucket(t.get("strike_distance"))} for t in self.trades], "dist_bucket")
    def regime_wise(self): return _group_by(self.trades, "regime")
    def walk_forward(self, folds: int = 5):
        if folds <= 0 or len(self.trades) < folds: return []
        size = len(self.trades) // folds
        return [{"fold": i + 1, **compute_metrics(self.trades[i*size:(i+1)*size])} for i in range(folds)]
    def out_of_sample(self, split: float = 0.7):
        split = min(1.0, max(0.0, float(split))); cut = int(len(self.trades) * split)
        return {"in_sample": compute_metrics(self.trades[:cut]), "out_of_sample": compute_metrics(self.trades[cut:])}
    def monte_carlo(self, iterations: int = 1000, seed: int = 42):
        iterations = max(0, int(iterations))
        if not self.trades: return {"iterations": iterations, "n": 0}
        if iterations == 0: return {"iterations": 0, "n": len(self.trades)}
        rng = random.Random(seed); rs = [float(t.get("r", 0.0) or 0.0) for t in self.trades]
        finals = sorted(sum(rng.choice(rs) for _ in rs) for _ in range(iterations))
        def pct(p): return finals[min(len(finals)-1, int(p*len(finals)))]
        return {"iterations": iterations, "n": len(rs), "p05": round(pct(.05),4), "p50": round(pct(.50),4), "p95": round(pct(.95),4), "prob_positive": round(sum(f > 0 for f in finals)/len(finals),4)}
    def cost_adjusted(self, default_slippage_r: float = 0.0, default_transaction_cost_r: float = 0.0):
        """Report gross and net expectancy using per-trade R costs, without hidden unit conversion."""
        gross = compute_metrics(self.trades)
        adjusted = []
        for trade in self.trades:
            gross_r = float(trade.get("r", 0.0) or 0.0)
            slip = max(0.0, float(trade.get("slippage_r", default_slippage_r) or 0.0))
            fees = max(0.0, float(trade.get("transaction_cost_r", default_transaction_cost_r) or 0.0))
            adjusted.append({**trade, "r": gross_r - slip - fees})
        net = compute_metrics(adjusted)
        return {"gross": gross, "net": net, "slippage_r": float(default_slippage_r),
                "transaction_cost_r": float(default_transaction_cost_r),
                "cost_basis": "R per trade; costs are explicit, not currency amounts"}

    def parameter_sensitivity(self, param: str): return _group_by(self.trades, param)
    def robustness(self):
        wf = self.walk_forward()
        if not wf: return {"robust": None, "note": "insufficient trades"}
        avgs = [f["average_r"] for f in wf if f["average_r"] is not None]
        if not avgs: return {"robust": None}
        mean = sum(avgs)/len(avgs); var = sum((a-mean)**2 for a in avgs)/len(avgs)
        return {"robust": var < .5 and mean > 0, "fold_mean_r": round(mean,4), "fold_std_r": round(math.sqrt(var),4)}
    def slippage_sensitivity(self, costs=None):
        costs = costs or [0.0,.02,.05,.1]
        return {f"slip_{c}": compute_metrics([{**t,"r":float(t.get("r",0.0) or 0.0)-c} for t in self.trades]) for c in costs}
    def transaction_cost_sensitivity(self, costs=None):
        costs = costs or [0.0,20.0,50.0,100.0]
        return {f"cost_{c}": compute_metrics([{**t,"r":float(t.get("r",0.0) or 0.0)-c/100.0} for t in self.trades]) for c in costs}
    def forward_paper_validation(self, live_trades): return {"paper": compute_metrics(live_trades), "note": "compare vs the backtest sample"}
    def drift_detection(self, live_trades):
        bt = compute_metrics(self.trades); live = compute_metrics(live_trades)
        if bt.get("average_r") is None or live.get("average_r") is None: return {"drift": None, "note": "need both samples"}
        drift = round(live["average_r"] - bt["average_r"],4)
        return {"backtest_avg_r": bt["average_r"], "live_avg_r": live["average_r"], "drift": drift, "alert": abs(drift) > .5}
    def full_report(self):
        return {"overall":self.overall(),"strategy_wise":self.strategy_wise(),"index_wise":self.index_wise(),"ce_vs_pe":self.ce_vs_pe(),"expiry_vs_non_expiry":self.expiry_vs_non_expiry(),"time_window":self.time_window(),"strike_distance":self.strike_distance(),"regime_wise":self.regime_wise(),"walk_forward":self.walk_forward(),"out_of_sample":self.out_of_sample(),"monte_carlo":self.monte_carlo(),"robustness":self.robustness(),"slippage":self.slippage_sensitivity(),"transaction_cost":self.transaction_cost_sensitivity(),"cost_adjusted":self.cost_adjusted()}
