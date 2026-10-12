from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .market_store import MarketStore


def resolve_totp(totp: str | None) -> str:
    code = (totp or "").strip()
    if not code:
        raise RuntimeError("Current 6-digit TOTP is required")
    if not code.isdigit() or len(code) != 6:
        raise RuntimeError("Current TOTP must be exactly 6 digits")
    return code


class AngelGateway:
    """Isolated SmartAPI boundary. No trading/order methods are exposed here."""

    INDEXES = {
        "NIFTY": {"exchange": "NSE", "segment": "NSE-FO"},
        "BANKNIFTY": {"exchange": "NSE", "segment": "NSE-FO"},
        "FINNIFTY": {"exchange": "NSE", "segment": "NSE-FO"},
        "MIDCPNIFTY": {"exchange": "NSE", "segment": "NSE-FO"},
        "SENSEX": {"exchange": "BSE", "segment": "BSE-FO"},
        "BANKEX": {"exchange": "BSE", "segment": "BSE-FO"},
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.client: Any | None = None
        self.client_code: str | None = None
        self.api_key: str | None = None
        self.auth_token: str | None = None
        self.refresh_token: str | None = None
        self.feed_token: str | None = None
        self.authenticated = False
        self.session_invalidated = False
        self.last_error: str | None = None
        self.stream_error: str | None = None
        self.stream: Any | None = None
        self.market_store = MarketStore()
        self._stream_lock = threading.Lock()
        self.last_stream_attempt_at: float | None = None
        self.last_stream_open_at: float | None = None
        self.last_tick_at: float | None = None
        self.websocket_tick_count = 0
        # Historical candles are shared across app screens; serialize requests and
        # cache exact queries to avoid duplicate SmartAPI calls during refreshes.
        self._historical_lock = threading.Lock()
        self._historical_cache: dict[tuple[str, str, str, str, str], tuple[float, list[list[Any]]]] = {}
        self._historical_last_request_at = 0.0
        self.stream_open = False

    def connect(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp: str | None = None,
    ) -> dict[str, Any]:
        try:
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError("smartapi-python is required") from exc

        with self._lock:
            self.last_error = None
            self.session_invalidated = False
            self.client_code = client_code.strip()
            self.api_key = api_key.strip()
            self.client = SmartConnect(api_key=self.api_key)
            try:
                code = resolve_totp(totp)
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc
            # Clear all previous session state before every login attempt. A
            # stale token must never make a failed login look authenticated.
            self.authenticated = False
            self.auth_token = None
            self.refresh_token = None
            self.feed_token = None
            session = self.client.generateSession(self.client_code, pin, code)
            if not isinstance(session, dict) or session.get("status") is not True:
                error_code = session.get("errorcode", "") if isinstance(session, dict) else ""
                message = session.get("message", "Angel One login failed") if isinstance(session, dict) else "Angel One returned an invalid login response"
                suffix = f" [{error_code}]" if error_code else ""
                if str(error_code) == "AB1050" or "invalid totp" in str(message).lower():
                    raise RuntimeError(
                        "Invalid/expired TOTP [AB1050]. Use the current 6-digit code, "
                        "check phone/server time."
                    )
                raise RuntimeError(f"Angel One login rejected: {message}{suffix}")

            data = session.get("data")
            data = data if isinstance(data, dict) else {}
            self.auth_token = data.get("jwtToken") or getattr(self.client, "access_token", None)
            self.refresh_token = data.get("refreshToken") or getattr(self.client, "refresh_token", None)
            self.feed_token = data.get("feedToken")
            if not self.feed_token:
                try:
                    self.feed_token = self.client.getfeedToken()
                except Exception:
                    self.feed_token = None

            if not self.auth_token or not self.feed_token:
                missing = []
                if not self.auth_token:
                    missing.append("jwtToken")
                if not self.feed_token:
                    missing.append("feedToken")
                self.last_error = "Angel login response lacked required token(s): " + ", ".join(missing)
                raise RuntimeError(self.last_error)

            # Keep SDK internals and the gateway state in sync before marking
            # the session authenticated or allowing a WebSocket to start.
            if hasattr(self.client, "setAccessToken"):
                self.client.setAccessToken(self.auth_token)
            if self.refresh_token and hasattr(self.client, "setRefreshToken"):
                self.client.setRefreshToken(self.refresh_token)
            if hasattr(self.client, "setFeedToken"):
                self.client.setFeedToken(self.feed_token)
            self.authenticated = True
            return {
                "authenticated": True,
                "client_code": self.client_code,
                "has_jwt_token": True,
                "has_feed_token": True,
                "login_message": str(session.get("message") or "Login successful"),
            }

    def invalidate_session(self, reason: str) -> None:
        """Fail closed when SmartAPI proves the JWT/session is no longer valid."""
        with self._lock:
            self.authenticated = False
            self.session_invalidated = True
            self.auth_token = None
            self.refresh_token = None
            self.feed_token = None
            self.stream_open = False
            self.stream_error = reason
            self.last_error = reason
            old_stream = self.stream
            self.stream = None
            if old_stream is not None:
                try:
                    old_stream.close_connection()
                except Exception:
                    pass

    @staticmethod
    def _is_invalid_token_error(error: Any) -> bool:
        message = str(error).lower()
        return any(marker in message for marker in (
            "invalid token", "ag8001", "token expired", "invalid jwt",
            "unauthorized", "401 unauthorized",
        ))

    def session_tokens(self) -> dict[str, str | None]:
        return {
            "api_key": self.api_key,
            "jwt": self.auth_token,
            "refresh": self.refresh_token,
            "feed": self.feed_token,
            "client_code": self.client_code,
        }

    def restore_session(
        self,
        *,
        api_key: str,
        client_code: str,
        jwt: str | None,
        refresh: str | None,
        feed: str | None,
    ) -> bool:
        """Restore a previously authenticated SmartAPI session without PIN/TOTP."""
        try:
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError("smartapi-python is required") from exc

        with self._lock:
            self.api_key = api_key.strip()
            self.client_code = client_code.strip()
            self.client = SmartConnect(
                api_key=self.api_key,
                access_token=jwt,
                refresh_token=refresh,
                feed_token=feed,
            )
            self.auth_token = jwt
            self.refresh_token = refresh
            self.feed_token = feed
            self.authenticated = bool(jwt and feed)

            if self.refresh_token:
                try:
                    refreshed = self.client.generateToken(self.refresh_token)
                    if refreshed and refreshed.get("status") and refreshed.get("data"):
                        data = refreshed["data"]
                        self.auth_token = data.get("jwtToken") or self.auth_token
                        self.feed_token = data.get("feedToken") or self.feed_token
                        self.refresh_token = data.get("refreshToken") or self.refresh_token
                        self.client.setAccessToken(self.auth_token)
                        self.client.setRefreshToken(self.refresh_token)
                        self.client.setFeedToken(self.feed_token)
                        self.authenticated = bool(self.auth_token and self.feed_token)
                except Exception:
                    # A still-valid stored JWT/feed token can continue without re-login.
                    pass

            self.last_error = None if self.authenticated else "Stored Angel session is no longer valid."
            return self.authenticated

    def stream_needs_restart(self, stale_after_seconds: int = 15) -> bool:
        if not self.authenticated:
            return False
        now = time.time()
        if self.stream is None:
            return self.last_stream_attempt_at is None or now - self.last_stream_attempt_at >= 15
        # A non-null SDK object is not proof that ticks are arriving.
        last_activity = self.last_tick_at or self.last_stream_open_at or self.last_stream_attempt_at
        if last_activity is None:
            return True
        return (
            now - last_activity > max(10, stale_after_seconds)
            and (self.last_stream_attempt_at is None or now - self.last_stream_attempt_at >= 30)
        )

    def start_stream(self, token_list: list[dict[str, Any]], on_tick: Callable[[dict[str, Any]], None] | None = None) -> None:
        if not self.client or not self.authenticated or not self.auth_token or not self.feed_token:
            raise RuntimeError("Angel One session is not connected")
        if not token_list or not any(item.get("tokens") for item in token_list):
            raise RuntimeError("No market tokens were supplied for WebSocket subscription")
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except ImportError as exc:
            raise RuntimeError("smartapi-python WebSocketV2 is required") from exc

        with self._stream_lock:
            now = time.time()
            if self.last_stream_attempt_at is not None and now - self.last_stream_attempt_at < 15:
                return
            old_stream = self.stream
            self.last_stream_attempt_at = now
            self.stream_open = False
            self.last_stream_open_at = None
            self.last_error = None
            self.stream_error = None
            if old_stream is not None:
                try:
                    old_stream.close_connection()
                except Exception:
                    pass
            self.stream = None

            def data_callback(_ws: Any, data: dict[str, Any]) -> None:
                if not isinstance(data, dict):
                    return
                normalized = dict(data)
                normalized["token"] = str(
                    normalized.get("token")
                    or normalized.get("symboltoken")
                    or normalized.get("symbolToken")
                    or ""
                )
                if not normalized["token"]:
                    self.last_error = "WebSocket tick received without an instrument token"
                    return
                if "last_traded_price" in normalized:
                    normalized["last_traded_price"] = float(normalized["last_traded_price"]) / 100.0
                if "open_interest" in normalized:
                    normalized["open_interest"] = float(normalized["open_interest"])
                bid, ask = self._best_bid_ask(normalized)
                if bid is not None:
                    normalized["best_bid"] = bid
                if ask is not None:
                    normalized["best_ask"] = ask
                normalized["source"] = "angel-one-websocket"
                self.market_store.update(normalized)
                self.last_tick_at = time.time()
                self.websocket_tick_count += 1
                if on_tick:
                    on_tick(normalized)

            def error_callback(_ws: Any, error: Any) -> None:
                self.stream_error = "WebSocket error: " + str(error)
                self.last_error = self.stream_error
                self.stream_open = False

            def close_callback(_ws: Any) -> None:
                self.stream_open = False
                self.stream = None
                if self.authenticated and self.stream_error is None:
                    self.stream_error = "WebSocket closed without a reported reason; feed health check will retry it."
                if self.stream_error:
                    self.last_error = self.stream_error

            ws = SmartWebSocketV2(
                self.auth_token,
                self.client.api_key,
                self.client_code,
                self.feed_token,
                # Allow more SDK reconnect attempts; API/status polling also
                # restarts the stream if the SDK ultimately gives up.
                max_retry_attempt=10,
                retry_strategy=1,
                retry_delay=5,
                retry_multiplier=2,
            )

            def open_callback(_ws: Any) -> None:
                self.stream_open = True
                self.stream_error = None
                self.last_stream_open_at = time.time()
                try:
                    ws.subscribe("fresh-live", 3, token_list)
                except Exception as exc:
                    self.stream_error = "WebSocket subscription failed: " + str(exc)
                    self.last_error = self.stream_error
                    self.stream_open = False

            ws.on_data = data_callback
            ws.on_error = error_callback
            ws.on_close = close_callback
            ws.on_open = open_callback
            self.stream = ws
            threading.Thread(target=ws.connect, name="fresh-angel-ws", daemon=True).start()

    @staticmethod
    def _book_price(value: Any) -> float | None:
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        return price / 100.0

    @classmethod
    def _best_bid_ask(cls, tick: dict[str, Any]) -> tuple[float | None, float | None]:
        groups: list[list[float]] = []
        for key in ("best_5_buy_data", "best_5_sell_data"):
            prices = []
            for row in tick.get(key) or []:
                if isinstance(row, dict):
                    price = cls._book_price(row.get("price"))
                    if price is not None:
                        prices.append(price)
            if prices:
                groups.append(prices)
        if len(groups) != 2:
            return None, None
        lower, upper = sorted(groups, key=lambda values: min(values))
        bid, ask = max(lower), min(upper)
        if ask < bid:
            return None, None
        return round(bid, 4), round(ask, 4)

    def historical_candles(
        self,
        *,
        exchange: str,
        token: str,
        interval: str,
        fromdate: str,
        todate: str,
    ) -> list[list[Any]]:
        if not self.client or not self.authenticated:
            raise RuntimeError("Angel One session is not connected")

        key = (exchange.upper(), str(token), interval.upper(), fromdate, todate)
        now = time.time()
        with self._historical_lock:
            cached = self._historical_cache.get(key)
            # Identical historical ranges are immutable enough for a short cache;
            # this prevents repeated tab refreshes from consuming broker quota.
            if cached and now - cached[0] <= 900:
                return [list(row) for row in cached[1]]

            # SmartAPI documents a 3 requests/second historical limit. Keep a
            # margin below that limit even when concurrent UI requests arrive.
            wait = 0.45 - (now - self._historical_last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._historical_last_request_at = time.time()

            try:
                response = self.client.getCandleData({
                    "exchange": exchange,
                    "symboltoken": str(token),
                    "interval": interval,
                    "fromdate": fromdate,
                    "todate": todate,
                })
            except Exception as exc:
                if self._is_invalid_token_error(exc):
                    self.invalidate_session("Invalid/expired Angel session token. Reconnect using the current TOTP.")
                # A failed request must not be silently converted into a success.
                raise

            if not isinstance(response, dict) or response.get("status") is not True:
                message = str((response or {}).get("message", "Historical candle request failed")) if isinstance(response, dict) else "Angel One returned a non-JSON historical response"
                error_code = str((response or {}).get("errorcode", "")).upper() if isinstance(response, dict) else ""
                if self._is_invalid_token_error(message) or error_code == "AG8001":
                    self.invalidate_session("Invalid/expired Angel session token. Reconnect using the current TOTP.")
                raise RuntimeError(f"Angel One historical candles failed [{error_code or 'NO_CODE'}]: {message}")

            rows = [row for row in (response.get("data") or []) if isinstance(row, (list, tuple)) and len(row) >= 6]
            normalized_rows = [list(row) for row in rows]
            self._historical_cache[key] = (time.time(), normalized_rows)
            # Bound memory if many date ranges are requested.
            if len(self._historical_cache) > 128:
                oldest = sorted(self._historical_cache, key=lambda item: self._historical_cache[item][0])[:32]
                for old_key in oldest:
                    self._historical_cache.pop(old_key, None)
            return [list(row) for row in normalized_rows]

    def status(self) -> dict[str, Any]:
        now = time.time()
        return {
            "authenticated": self.authenticated,
            "stream_started": self.stream is not None,
            "stream_open": self.stream_open,
            "client_code": self.client_code,
            "last_error": self.last_error,
            "stream_error": self.stream_error,
            "tick_count": self.websocket_tick_count,
            "unique_tokens_seen": len(self.market_store.snapshot()),
            "last_tick_at": datetime.fromtimestamp(self.last_tick_at, timezone.utc).isoformat() if self.last_tick_at else None,
            "last_tick_age_seconds": round(now - self.last_tick_at, 1) if self.last_tick_at else None,
            "last_stream_attempt_at": datetime.fromtimestamp(self.last_stream_attempt_at, timezone.utc).isoformat() if self.last_stream_attempt_at else None,
        }

    def market_data(self, exchange: str, tokens: list[str], mode: str = "FULL") -> dict[str, Any]:
        if not self.client or not self.authenticated:
            raise RuntimeError("Angel One session is not connected")
        return self.client.getMarketData(mode, {exchange: tokens})

    def market_data_multi(self, exchange_tokens: dict[str, list[str]], mode: str = "LTP") -> dict[str, Any]:
        if not self.client or not self.authenticated:
            raise RuntimeError("Angel One session is not connected")
        cleaned = {
            str(exchange).upper(): [str(token) for token in tokens if str(token).strip()]
            for exchange, tokens in exchange_tokens.items()
            if tokens
        }
        if not cleaned:
            raise RuntimeError("No exchange tokens supplied for REST market data")
        if sum(len(tokens) for tokens in cleaned.values()) > 50:
            raise RuntimeError("SmartAPI market-data request exceeds 50-symbol limit")
        try:
            response = self.client.getMarketData(mode, cleaned)
        except Exception as exc:
            if self._is_invalid_token_error(exc):
                self.invalidate_session("Invalid/expired Angel session token. Reconnect using the current TOTP.")
            raise
        if isinstance(response, dict) and (
            response.get("status") is False
            and (self._is_invalid_token_error(response.get("message", "")) or str(response.get("errorcode", "")).upper() == "AG8001")
        ):
            self.invalidate_session("Invalid/expired Angel session token. Reconnect using the current TOTP.")
            raise RuntimeError(self.last_error or "Invalid Angel session token")
        return response

    def holdings(self) -> Any:
        if not self.client or not self.authenticated:
            raise RuntimeError("Angel One session is not connected")
        return self.client.holding()

    def positions(self) -> Any:
        if not self.client or not self.authenticated:
            raise RuntimeError("Angel One session is not connected")
        return self.client.position()
