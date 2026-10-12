# Angel One SmartAPI Live Feed Runbook

This project uses **Angel One SmartAPI**, not Zerodha Kite. The Python backend uses the official `smartapi-python` package and `SmartWebSocketV2`; the Android app connects only to the hosted HTTPS backend.

## Runtime path

1. The app submits Angel One API key, client ID, PIN/MPIN and current six-digit TOTP to the backend login endpoint.
2. The backend calls `SmartConnect.generateSession()`, validates the success response, and requires both JWT and feed token before marking the session authenticated.
3. The instrument master is downloaded from Angel One's OpenAPI Scrip Master and cached. Do not hard-code sample tokens from blog posts; resolve symbols/tokens and exchange segments from the current master.
4. The backend starts `SmartWebSocketV2` in a daemon thread and subscribes to a bounded token list in full mode for market/OI/depth fields.
5. Incoming ticks are normalized into the shared `MarketStore`; the signal, OI, chart and data-health views read from the same store.
6. REST market quotes are used as a fallback where available. REST fallback must be labelled separately from WebSocket live data.
7. The app exposes feed diagnostics including authenticated status, WebSocket open status, tick count, unique tokens, last tick age and last error.

## Useful endpoints

- `GET /health` — backend health.
- `GET /v1/angel/status` — session/feed diagnostics (see the current API routes if route names change).
- `POST /v1/angel/connect` — authenticate with Angel One credentials and current TOTP.
- `POST /v1/instruments/sync` — refresh/cache the broker instrument master.
- `POST /v1/stream/start` — start subscriptions for selected supported indexes.
- `GET /v1/market/ticks` — normalized tick store and diagnostics.
- `GET /v1/signals` — normalized market snapshots, option-chain rows, signal decisions, AI results and feed health.

Use the actual OpenAPI schema at `/docs` on the deployed backend as the source of truth for endpoint methods and request payloads.

## Feed modes and data quality

The SDK's WebSocket subscription modes are commonly LTP (1), quote (2), and full (3). This project uses full mode for the live stream because downstream OI/depth processing may need fields beyond LTP. A successful login or an open socket is **not** proof that prices are arriving: check the last-tick age and per-index data source.

- Fresh WebSocket ticks should identify their source as `angel-one-websocket`.
- REST quote fallback is labelled `angel-one-rest-fallback`.
- Stale/cached values must not be presented as live.
- Missing index/option tokens, invalid session, stale ticks, incomplete quote/depth, unknown lot size, wide spread, strategy conflict or risk-limit failure must prevent live-order qualification.
- Reconnect/restart logic and feed diagnostics are implemented in `backend/app/angel.py`; inspect deployed logs when `stream_open` remains false or `tick_count` does not increase.
- The official instrument master, SDK and API documentation can change. Verify exchange-specific subscription token types and current rate limits against the official documentation before production use.

## Security and rollout

- Keep API keys, PIN, TOTP seed and broker session tokens on the backend; never package them into the Android APK or commit them to Git.
- Configure secrets using Railway variables or the encrypted backend credential store.
- Verify backend health, then authenticate, sync instruments, start the stream and confirm ticks on `/v1/market/ticks` before checking OI/signals.
- Keep real-order execution disabled while validating feed quality. Use paper trading and walk-forward/out-of-sample checks first. A UI link to a third-party repository is only a reference, not integrated code.

## Official/reference links

- Official Python SDK: https://github.com/angel-one/smartapi-python
- SmartWebSocketV2 implementation: https://github.com/angel-one/smartapi-python/blob/main/SmartApi/smartWebSocketV2.py
- Official JavaScript SDK: https://github.com/angel-one/smartapi-javascript
- SmartAPI docs: https://smartapi.angelone.in/docs
- Angel One documentation guide: https://www.angelone.in/knowledge-center/smartapi/making-sense-of-the-smartapi-documentation
- FastAPI dashboard reference: https://github.com/dngr2/fastapi-trading-dashboard
- Full-stack paper trading reference: https://github.com/suryakalla06/paper-trading
