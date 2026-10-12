"""Signal-only order-book imbalance (OBI) strategy for normalized Angel ticks.

Depth prices from SmartAPI are paise; normalized LTP is rupees. No order APIs.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class OBIParams:
    obi_threshold: float = 0.35
    obi_alpha: float = 0.30
    min_micro_edge_bps: float = 0.30
    max_spread_bps: float = 8.0
    momentum_ticks: int = 5
    persistence: int = 3
    cooldown_sec: float = 3.0
    stale_after_sec: float = 5.0


class OBIEngine:
    """Thread-safe per-token OBI state, exposing the latest signal/diagnostics."""

    def __init__(self, params: OBIParams | None = None) -> None:
        self.params = params or OBIParams()
        self._lock = threading.RLock()
        self._states: dict[str, dict[str, Any]] = {}
        self._latest: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _levels(raw: Any) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        if not isinstance(raw, list):
            return out
        for row in raw[:5]:
            if not isinstance(row, dict):
                continue
            try:
                price = float(row.get("price", 0)) / 100.0
                qty = float(row.get("quantity", row.get("quantity", 0)))
            except (TypeError, ValueError):
                continue
            if math.isfinite(price) and math.isfinite(qty) and price > 0 and qty > 0:
                out.append((price, qty))
        return out

    def on_tick(self, tick: dict[str, Any]) -> None:
        token = str(tick.get("token") or "").strip()
        if not token or not token.isdigit():
            return
        try:
            ltp = float(tick.get("last_traded_price", tick.get("ltp", 0)))
        except (TypeError, ValueError):
            return
        if not math.isfinite(ltp) or ltp <= 0:
            return
        bids = self._levels(tick.get("best_5_buy_data"))
        asks = self._levels(tick.get("best_5_sell_data"))
        now = time.time()
        if not bids or not asks:
            with self._lock:
                self._latest[token] = {
                    "token": token, "symbol": str(tick.get("symbol") or token),
                    "status": "WAIT", "reason": "Five-level bid/ask depth unavailable",
                    "timestamp": datetime.now(IST).isoformat(), "source": tick.get("source", "unknown"),
                }
            return
        best_bid, bid_q1 = bids[0]
        best_ask, ask_q1 = asks[0]
        if best_bid <= 0 or best_ask <= best_bid or bid_q1 + ask_q1 <= 0:
            return
        bid_qty = sum(q for _, q in bids)
        ask_qty = sum(q for _, q in asks)
        if bid_qty + ask_qty <= 0:
            return
        mid = (best_bid + best_ask) / 2
        spread_bps = (best_ask - best_bid) / mid * 10000
        # Correct size-weighted microprice: bid weighted by bid size,
        # ask weighted by ask size.
        micro = (best_ask * bid_q1 + best_bid * ask_q1) / (bid_q1 + ask_q1)
        micro_edge_bps = (micro - mid) / mid * 10000
        obi = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        p = self.params
        with self._lock:
            state = self._states.setdefault(token, {
                "ema": None, "ltps": deque(maxlen=p.momentum_ticks + 1),
                "streak_side": None, "streak": 0, "last_signal": 0.0,
            })
            state["ema"] = obi if state["ema"] is None else p.obi_alpha * obi + (1 - p.obi_alpha) * state["ema"]
            state["ltps"].append(ltp)
            diagnostics = {
                "token": token, "symbol": str(tick.get("symbol") or token),
                "status": "WAIT", "reason": "Collecting momentum history",
                "ltp": ltp, "obi": round(state["ema"], 4),
                "micro_edge_bps": round(micro_edge_bps, 3),
                "spread_bps": round(spread_bps, 3),
                "timestamp": datetime.now(IST).isoformat(),
                "source": tick.get("source", "unknown"),
            }
            if len(state["ltps"]) < p.momentum_ticks + 1:
                self._latest[token] = diagnostics
                return
            momentum = (state["ltps"][-1] - state["ltps"][0]) / state["ltps"][0] * 10000
            diagnostics["momentum_bps"] = round(momentum, 3)
            if spread_bps > p.max_spread_bps:
                state["streak_side"], state["streak"] = None, 0
                diagnostics["reason"] = "Spread exceeds configured maximum"
            else:
                side = None
                if state["ema"] >= p.obi_threshold and micro_edge_bps >= p.min_micro_edge_bps and momentum >= 0:
                    side = "BUY"
                elif state["ema"] <= -p.obi_threshold and micro_edge_bps <= -p.min_micro_edge_bps and momentum <= 0:
                    side = "SELL"
                if side is None:
                    state["streak_side"], state["streak"] = None, 0
                    diagnostics["reason"] = "OBI, microprice and momentum not aligned"
                else:
                    if state["streak_side"] == side:
                        state["streak"] += 1
                    else:
                        state["streak_side"], state["streak"] = side, 1
                    diagnostics["reason"] = "Confirming persistent imbalance"
                    if state["streak"] >= p.persistence and now - state["last_signal"] >= p.cooldown_sec:
                        state["last_signal"] = now
                        state["streak_side"], state["streak"] = None, 0
                        diagnostics.update({
                            "status": side, "reason": "OBI filters confirmed",
                            "reference_price": best_ask if side == "BUY" else best_bid,
                        })
            self._latest[token] = diagnostics

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            items = {}
            for token, item in self._latest.items():
                row = dict(item)
                try:
                    ts = datetime.fromisoformat(str(row["timestamp"]))
                    age = max(0.0, (datetime.now(IST) - ts.astimezone(IST)).total_seconds())
                except (ValueError, KeyError):
                    age = float("inf")
                row["age_seconds"] = round(age, 1) if math.isfinite(age) else None
                if age > self.params.stale_after_sec:
                    row["status"] = "WAIT"
                    row["reason"] = "OBI tick is stale; no fresh signal"
                items[token] = row
            return {
                "strategy": "HFT-style OBI (signal-only)",
                "order_placement_enabled": False,
                "count": len(items),
                "signals": items,
                "generated_at": datetime.now(IST).isoformat(),
            }
