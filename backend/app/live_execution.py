from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
import math
import os
import threading
import time
from typing import Any


IST = ZoneInfo("Asia/Kolkata")
LIVE_CONFIRMATION = "PLACE_REAL_ANGEL_ORDER"


class LiveExecutionError(RuntimeError):
    pass


class LiveExecutionService:
    """Explicitly gated Angel One order execution with fail-closed checks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = datetime.now(IST).date()
        self._orders_today = 0
        self._order_ids: list[str] = []
        self._request_ids: dict[str, dict[str, Any]] = {}

    @staticmethod
    def enabled() -> bool:
        return os.getenv("FRESH_LIVE_TRADING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def max_orders_per_day() -> int:
        try:
            return max(1, min(100, int(os.getenv("FRESH_MAX_LIVE_ORDERS_PER_DAY", "5"))))
        except ValueError:
            return 5

    @staticmethod
    def max_order_notional() -> float:
        try:
            return max(1000.0, min(1_000_000.0, float(os.getenv("FRESH_MAX_LIVE_ORDER_NOTIONAL_INR", "10000"))))
        except ValueError:
            return 10000.0

    def _roll_day(self) -> None:
        today = datetime.now(IST).date()
        if self._day != today:
            self._day = today
            self._orders_today = 0
            self._order_ids = []
            self._request_ids = {}

    def status(self, gateway: Any) -> dict[str, Any]:
        with self._lock:
            self._roll_day()
            return {
                "broker": "Angel One SmartAPI",
                "mode": "LIVE" if self.enabled() else "DISABLED",
                "live_execution_enabled": self.enabled(),
                "authenticated": bool(gateway.authenticated),
                "stream_open": bool(gateway.stream_open),
                "tick_count": int(gateway.websocket_tick_count),
                "last_tick_age_seconds": gateway.status().get("last_tick_age_seconds"),
                "orders_today": self._orders_today,
                "max_orders_per_day": self.max_orders_per_day(),
                "max_order_notional_inr": self.max_order_notional(),
                "real_orders_possible": self.enabled() and bool(gateway.authenticated),
                "confirmation_phrase_required": LIVE_CONFIRMATION,
                "automatic_signal_execution": False,
                "note": "The endpoint submits real broker orders only after an explicit request; automatic signal execution is not enabled.",
            }

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @staticmethod
    def _strike_value(row: dict[str, Any]) -> float | None:
        value = LiveExecutionService._number(row.get("strike"))
        if value is None or value <= 0:
            return None
        return value / 100.0 if value >= 100000 else value

    def execute_qualified_signal(
        self,
        *,
        gateway: Any,
        master: Any,
        store: Any,
        index: str,
        lots: int,
        confirmation: str,
        request_id: str,
        stale_after_seconds: int,
        signal: Any,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise LiveExecutionError("Live execution is disabled. Set FRESH_LIVE_TRADING_ENABLED=true on the backend to enable real orders.")
        if confirmation != LIVE_CONFIRMATION:
            raise LiveExecutionError(f"Explicit confirmation required: {LIVE_CONFIRMATION}")
        if not gateway.authenticated or gateway.client is None:
            raise LiveExecutionError("Angel One is not authenticated.")
        if not request_id or len(request_id) < 8 or len(request_id) > 100:
            raise LiveExecutionError("A unique request_id (8-100 characters) is required for duplicate protection.")
        if not isinstance(lots, int) or not 1 <= lots <= 10:
            raise LiveExecutionError("lots must be an integer between 1 and 10.")
        if signal is None:
            raise LiveExecutionError("No current strategy signal is available.")
        decision = getattr(getattr(signal, "decision", None), "value", getattr(signal, "decision", None))
        if decision not in {"CALL BUY", "PUT BUY"}:
            raise LiveExecutionError("Only a qualified CALL BUY or PUT BUY strategy can be executed.")
        if getattr(signal, "guards", None):
            raise LiveExecutionError("Strategy has safety guards; no order will be placed.")
        strike = self._number(getattr(signal, "strike", None))
        side = str(getattr(signal, "option_side", "") or "").upper()
        if strike is None or side not in {"CE", "PE"}:
            raise LiveExecutionError("Signal has no valid option strike/side.")
        if (decision == "CALL BUY" and side != "CE") or (decision == "PUT BUY" and side != "PE"):
            raise LiveExecutionError("Signal direction and selected option side disagree.")
        if not master.rows and not master.load_cache():
            raise LiveExecutionError("Instrument master is unavailable.")

        candidates = []
        for row in master.option_rows(index.upper()):
            row_strike = self._strike_value(row)
            if row_strike is None or abs(row_strike - strike) > 0.001:
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol.endswith(side):
                continue
            if str(row.get("exch_seg") or "").upper() not in {"NFO", "BFO"}:
                continue
            if "OPT" not in str(row.get("instrumenttype") or "").upper():
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise LiveExecutionError(f"Could not resolve exactly one active {index.upper()} {strike:g}{side} contract from Angel One instrument master.")

        instrument = candidates[0]
        token = str(instrument.get("token") or "").strip()
        symbol = str(instrument.get("symbol") or "").strip()
        exchange = str(instrument.get("exch_seg") or "").upper()
        lot_size_raw = self._number(instrument.get("lotsize"))
        if not token or not symbol or lot_size_raw is None or lot_size_raw <= 0:
            raise LiveExecutionError("Instrument master row is missing token, symbol, or valid lot size.")
        lot_size = int(lot_size_raw)
        quantity = lots * lot_size

        tick = store.get(token)
        if not tick:
            raise LiveExecutionError("No live quote exists for the selected option.")
        received_at = self._number(tick.get("received_at"))
        if received_at is None or time.time() - received_at > max(1, stale_after_seconds):
            raise LiveExecutionError("Selected option quote is stale; no order will be placed.")
        if str(tick.get("source") or "").startswith("angel-one-rest-fallback"):
            raise LiveExecutionError("REST fallback quote is not accepted for live entry; wait for a WebSocket tick.")
        ask = self._number(tick.get("best_ask"))
        ltp = self._number(tick.get("last_traded_price") or tick.get("ltp"))
        if ask is None or ask <= 0:
            raise LiveExecutionError("Live best ask is missing; no limit order will be placed.")
        if ltp is None or ltp <= 0:
            raise LiveExecutionError("Invalid live LTP.")
        if ask < ltp * 0.5 or ask > ltp * 1.5:
            raise LiveExecutionError("Best ask deviates abnormally from LTP; order rejected.")
        notional = ask * quantity
        if notional > self.max_order_notional():
            raise LiveExecutionError(f"Order notional ₹{notional:.2f} exceeds configured cap ₹{self.max_order_notional():.2f}.")

        with self._lock:
            self._roll_day()
            if request_id in self._request_ids:
                return {**self._request_ids[request_id], "duplicate_request": True}
            if self._orders_today >= self.max_orders_per_day():
                raise LiveExecutionError("Daily live-order limit reached.")
            self._request_ids[request_id] = {"status": "SUBMITTING", "request_id": request_id}

        try:
            positions_response = gateway.positions()
            if not isinstance(positions_response, dict) or positions_response.get("status") is False:
                raise LiveExecutionError("Could not verify broker positions; live entry blocked.")
            positions = positions_response.get("data") or []
            if not isinstance(positions, list):
                raise LiveExecutionError("Unexpected Angel One positions response; live entry blocked.")
            for position in positions:
                if not isinstance(position, dict) or str(position.get("tradingsymbol") or "") != symbol:
                    continue
                net_qty = int(self._number(position.get("netqty") or position.get("netQty") or position.get("quantity")) or 0)
                if net_qty != 0:
                    raise LiveExecutionError("An open position already exists for this contract; duplicate entry blocked.")

            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": "BUY",
                "exchange": exchange,
                "ordertype": "LIMIT",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": f"{ask:.2f}",
                "quantity": str(quantity),
                "squareoff": "0",
                "stoploss": "0",
            }
            response = gateway.client.placeOrder(order_params)
            if isinstance(response, dict):
                if response.get("status") is False:
                    raise LiveExecutionError("Angel One rejected the order: " + str(response.get("message") or response.get("errorcode") or "unknown broker rejection"))
                data = response.get("data")
                order_id = (data.get("orderid") or data.get("orderId")) if isinstance(data, dict) else response.get("orderid")
            else:
                order_id = response
            if not order_id:
                raise LiveExecutionError("Order submission response had no order ID; check Angel One order book before retrying.")
            result = {
                "status": "SUBMITTED",
                "broker": "Angel One SmartAPI",
                "order_id": str(order_id),
                "request_id": request_id,
                "index": index.upper(),
                "symbol": symbol,
                "token": token,
                "exchange": exchange,
                "decision": decision,
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "quantity": quantity,
                "lots": lots,
                "lot_size": lot_size,
                "limit_price": round(ask, 2),
                "reference_ltp": round(ltp, 2),
                "estimated_notional_inr": round(notional, 2),
                "stop_loss_reference": getattr(signal, "stop_loss", None),
                "target_reference": getattr(signal, "target", None),
                "note": "SUBMITTED is not the same as filled. Verify the broker order book/trade book.",
            }
            with self._lock:
                self._orders_today += 1
                self._order_ids.append(str(order_id))
                self._request_ids[request_id] = result
            return result
        except Exception as exc:
            with self._lock:
                self._request_ids.pop(request_id, None)
            if isinstance(exc, LiveExecutionError):
                raise
            raise LiveExecutionError("Angel One order submission failed; inspect broker order book before retrying: " + str(exc)) from exc
