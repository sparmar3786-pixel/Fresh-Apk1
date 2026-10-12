# Live Angel One Signal Pipeline

This project uses **Angel One SmartAPI only** for broker market data and any explicitly requested broker execution. It does not use Zerodha KiteConnect.

## Repository review

Useful references reviewed before integrating into Fresh-Apk:

- [Vandana1 trade verifier](https://github.com/sparmar3786-pixel/Vandana1/blob/main/backend/trade_verifier.py): market-data vs AI-plan checks and fail-closed verification.
- [Vandana1 AI verifier](https://github.com/sparmar3786-pixel/Vandana1/blob/main/backend/strategy_ai_verifier.py): AI is an auditor, not the owner of strategy direction.
- [Vandana1 Angel data layer](https://github.com/sparmar3786-pixel/Vandana1/blob/main/backend/angel_data_layer.py): normalize candle data and reject bad timestamps/rows.
- [VSP1 strategy pipeline](https://github.com/sparmar3786-pixel/VSP1/blob/main/backend/strategy_pipeline.py): out-of-sample evaluation and AI downgrade-only consensus.
- [HFT_System](https://github.com/AbhigyanD/HFT_System): useful C++ risk/matching examples, but its README says market data is synthetic, so it is not used as a live data source.
- [ruvnet/hft](https://github.com/ruvnet/hft): scaffold/reference only; not an Angel One connector.
- [pyKiteConnect](https://github.com/zerodha/pykiteconnect): Zerodha-only client and deliberately excluded.

The implementation in this repository is an adaptation of those ideas into Fresh-Apk's existing models and Angel One feed, not a wholesale copy of incompatible broker-specific code.

## Live decision lifecycle

1. Angel One SmartAPI session authenticates on the backend.
2. Angel One WebSocket ticks feed the normalized MarketStore.
3. The strategy runtime builds index snapshots, option candidates, OI changes and 1m/5m/15m context.
4. Deterministic strategy and trade-plan gates produce a candidate (CALL BUY, PUT BUY, WAIT, or NO TRADE).
5. For a qualifying candidate, the AI loop sends the current evidence packet plus available Exa/Tavily/Brave search evidence to OpenAI. The AI may confirm or downgrade; it may not reverse the deterministic direction.
6. backend/app/live_validation.py independently checks snapshot freshness/source, strategy guards/confidence, option-side/strike match, fresh bid/ask quote, spread, entry/SL/target ordering, reward/risk, AI freshness/confidence/direction, and AI risk flags.
7. The app's primary final signal is the validated decision. Any failed check returns WAIT and lists the blocking reasons.
8. Real order submission is separately gated by the live-order environment flag, explicit confirmation phrase, current qualified strategy, the same live AI validation PASS, current WebSocket option quote, contract/lot-size lookup, notional/order limits and broker position checks.

## Signal meaning

- BUY direction is emitted only after validation PASS for CALL BUY (bullish; call option).
- SELL direction is emitted only after validation PASS for PUT BUY (bearish; put option bought, not naked option selling).
- WAIT: data, AI, timeframe, quote, spread or risk validation is pending/failed.
- NO TRADE: no valid candidate or insufficient data.

These are not naked short-option SELL instructions. The platform should never fabricate a BUY/SELL call just to avoid WAIT.

## Current limits

- OpenAI must be configured to get an AI-confirmed signal. Without it, live validation remains WAIT.
- The selected option must have a fresh Angel One WebSocket quote with valid bid/ask; a REST fallback alone cannot pass live validation.
- SUBMITTED means the broker accepted an order request with an order ID; it does not prove fill.
- Automatic stop-loss/target order management is not yet complete. The returned SL/target are references, not an assurance of an automatic exit.
- This system does not promise profitability or exchange-colocated high-frequency execution. Real order execution requires broker/API permissions and applicable static-IP allowlisting.

## Relevant code

- backend/app/angel.py — Angel One SmartAPI session and WebSocket.
- backend/app/market_store.py — normalized ticks and freshness diagnostics.
- backend/app/signal_runtime.py — snapshots, timeframes, options and deterministic candidates.
- backend/app/ai.py — structured OpenAI decision and direction guard.
- backend/app/live_validation.py — final live candidate validation.
- backend/app/live_execution.py — explicitly gated real Angel One order submission.
- backend/tests/test_live_validation.py — freshness, direction, quote, spread and guard tests.