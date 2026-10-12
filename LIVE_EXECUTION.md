# Angel One live execution

Fresh-Apk uses the Angel One SmartAPI SDK. Zerodha Kite credentials and `kiteconnect` calls are not used.

## Safety defaults

- `FRESH_LIVE_TRADING_ENABLED=false` by default. Keep it false until login, live WebSocket ticks, option contract mapping and broker positions have been verified.
- The real-order endpoint requires the exact confirmation phrase `PLACE_REAL_ANGEL_ORDER` and a unique `request_id` to reduce accidental submissions and double taps.
- Only a currently qualified `CALL BUY` / `PUT BUY` strategy with no safety guards can be submitted.
- The selected option must resolve to exactly one active NFO/BFO option in the Angel instrument master.
- The selected contract must have a fresh Angel WebSocket quote and best ask. REST fallback and stale quotes are rejected.
- The quantity is derived from the exchange instrument master lot size; the caller specifies lots (1-10), not arbitrary units.
- Existing net positions in the same contract, daily order cap, and order-notional cap are checked before submission.
- Orders are LIMIT BUY orders. A response of `SUBMITTED` does not mean filled; inspect the broker order book and trade book.
- This endpoint does not yet automatically monitor and square off positions at stop-loss/target. The strategy stop/target are returned as references only. Do not treat this as a fully autonomous managed bot until the exit manager is implemented and verified.

## Backend environment

Set on Railway only after reviewing the limits:

```env
FRESH_LIVE_TRADING_ENABLED=true
FRESH_MAX_LIVE_ORDERS_PER_DAY=5
FRESH_MAX_LIVE_ORDER_NOTIONAL_INR=10000
```

Never put broker credentials in the APK or commit real credentials to Git.

## Endpoints

- `GET /v1/live/status` — mode, feed health and limits.
- `POST /v1/live/execute-signal` — submits a real Angel One LIMIT BUY for the current qualified option signal.
- `GET /v1/live/orders` — reads the broker order book.

Example request body (use only when the operator intends a real order):

```json
{
  "index": "NIFTY",
  "lots": 1,
  "confirmation": "PLACE_REAL_ANGEL_ORDER",
  "request_id": "unique-client-generated-id-123"
}
```

All endpoints require the app's valid `X-Device-ID` header. This is a guarded live-order integration, not a claim of guaranteed profitability or high-frequency exchange co-location.
