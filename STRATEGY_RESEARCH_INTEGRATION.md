# Strategy, Backtest and UI Research Integration

This document records which supplied GitHub references were inspected, which concepts were adapted, and what is deliberately not claimed as integrated.

## Repository audit

- [paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) and [joelowj/awesome-algorithmic-trading](https://github.com/joelowj/awesome-algorithmic-trading) are curated directories. They are not one importable strategy engine.
- [wilsonfreitas/awesome-quant](https://github.com/wilsonfreitas/awesome-quant) and [cbailes/awesome-deep-trading](https://github.com/cbailes/awesome-deep-trading) are research catalogues; their entries have distinct dependencies and data assumptions.
- [JasonTeixeira/trade-engine](https://github.com/JasonTeixeira/trade-engine) uses a risk manager between signals and order submission and models order lifecycle states. Its repository did not expose a license in the API audit, so source code was not copied. Fresh retains its own backend and guarded Angel One order path.
- [tripolskypetr/backtest-kit](https://github.com/tripolskypetr/backtest-kit) is TypeScript and MIT-licensed. Its documented concerns include look-ahead bias, order/fill state and restart safety. Fresh's Python candle replay independently uses next-bar-open entries, conservative stop-first ordering when a bar hits both stop and target, and explicit cost deductions; it is not a source-code port.
- [karimcodes/systematic-trading](https://github.com/karimcodes/systematic-trading) is Python/MIT and includes backtest and risk-management modules. Its capital/daily-loss defaults are strategy-specific and were not copied as universal settings.
- [Jaydot33/automated-trading-system](https://github.com/Jaydot33/automated-trading-system) is Python/MIT, but its documented backtest engine includes demonstration/mock-data assumptions. Its synthetic outputs are not used as live market evidence.
- [dngr2/fastapi-trading-dashboard](https://github.com/dngr2/fastapi-trading-dashboard) is a FastAPI/WebSocket dashboard reference. It is not the Angel One broker SDK.
- [lNamelessl/fastapi-fullstack-railway](https://github.com/lNamelessl/fastapi-fullstack-railway) is a deployment template reference; it does not prove the user's Railway service is deployed.
- [likhith1542/groww-clone](https://github.com/likhith1542/groww-clone) is a ReactJS UI prototype. It informed only the card-based information hierarchy for new screens; no Groww branding/assets or React runtime were copied into the Flutter APK.
- [angel-one/smartapi-python](https://github.com/angel-one/smartapi-python) is the official broker SDK reference. The backend's existing AngelGateway remains the broker boundary.
- Two links supplied in the documents could not be retrieved as public GitHub repositories during this audit: `hyuwowo/opentrading` and `Ritik5Prasad/GrowwClone_Public`. They are not treated as available code sources.

## Implemented in Fresh-Apk

### Historical backtest

- Added `backend/backtest/historical.py` and `POST /v1/backtest/historical`.
- Uses real Angel One historical index candles; validates OHLCV rows and deduplicates timestamps.
- Replays EMA crossovers with ATR-derived stops/targets, next-candle-open entries, max-hold/time exits, and explicit R-multiple slippage/transaction-cost assumptions.
- If both stop and target fall inside the same candle, the stop is assumed first.
- The UI no longer sends an empty hardcoded trade list to the backtest endpoint; users configure the period, index, interval and parameters, then run the replay.

**Scope limit:** this is an index-spot proxy backtest, not historical option-premium P&L. It does not simulate historical option quotes, changing strike/expiry selection, Greeks, or realistic option bid/ask fills. It must not be used to claim an option strategy has been validated.

### Technical indicators

The strategy output now includes OHLC-derived EMA50/EMA200, stochastic %K/%D, Williams %R, ROC10, ADX14, Supertrend direction and 20-bar support/resistance when normalized OHLC history is available. Insufficient data displays `N/A`, never an invented value. Existing EMA, RSI, MACD, ATR, VWAP, Bollinger, z-score and realized-volatility outputs remain.

### App behavior

- Removed the Paper Trades tab from APK navigation.
- Added the Research Engines tab, which displays actual current backend indicators, OI, research-pack checks, signal validation and AI status, plus the eight non-chart research links from the indicator/repository references.
- The pro Option Chain tab shows a horizontally scrollable quote table, CE/PE filter, strike/OI/volume sorting, ATM marker, quote age, and optional Greeks only when returned by the feed.
- Data Health shows backend/session state and per-index freshness. Raw feed diagnostics and normalized-store internals are hidden there.
- Trading Setup now includes a nine-module readiness checklist derived from current backend state.
- The 3-Layer Trade Engine remains signal candidate → deterministic risk/validation → gated execution status. A UI status is not proof of broker fill, and live order placement is not automatically enabled.

## Validation expectations

- Backend unit tests cover historical candle validation, insufficient history, indicator outputs and stale timestamp handling.
- Flutter widget tests cover tab navigation, Research Engines, Backtesting, Option Chain, Data Health and the 3-Layer Trade Engine.
- CI success only proves the code passed that workflow. It does not prove the deployed Railway service is connected to the user's Angel One account or that a live market feed is fresh.
