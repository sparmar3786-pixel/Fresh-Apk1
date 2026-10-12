# Strategy Registry

## Core deterministic rules implemented

### Trend
- EMA 8 vs EMA 13
- MACD 12/26 direction
- RSI 14
- VWAP context

### Volatility
- ATR 14
- Optional IV / Greeks fields from option feed

### Derivatives/OI
- Premium up + OI up = LONG BUILDUP
- Premium down + OI up = SHORT BUILDUP
- Premium up + OI down = SHORT COVERING
- Premium down + OI down = LONG UNWINDING
- PCR
- CE OI delta vs PE OI delta
- Opposite-side OI override

### Strike selection
- Target side (CE for bullish, PE for bearish)
- OI weight
- Volume/liquidity weight
- OI delta weight
- Premium momentum weight

### Risk
- Entry premium
- ATR-derived stop
- ATR-derived target
- Stale-data blocking
- Missing-chain blocking
- Mixed-regime -> WAIT

## AI interpretation layers

1. Data Quality
2. Market Regime
3. Technicals
4. Derivatives/OI
5. Risk
6. Final Decision

## Future extension slots

The architecture can add Bollinger Bands, Stochastic, ADX, Supertrend, volume profile, support/resistance, IV rank, max pain, expiry/time decay, spread/liquidity checks and historical backtest statistics without changing the API contract.


## Broker and system architecture

- Broker integration target: **Angel One SmartAPI** (REST + WebSocket); Zerodha/Kite is not required.
- Official SDK reference: https://github.com/angel-one/smartapi-python
- Official documentation: https://smartapi.angelone.in/docs
- Data-quality gate: timestamp/freshness, missing fields, abnormal ticks, instrument/expiry mapping, quote spread and feed disconnect checks.
- Signal filter: deterministic technical/OI evidence, cross-strategy conflict handling, AI evidence with missing-data flags, WAIT/NO TRADE fallback.
- Validation: walk-forward and out-of-sample backtesting, slippage/brokerage assumptions, and device-persisted paper-trade monitoring.
- Risk: lot-size and liquidity validation, premium-based stop/targets, risk/reward, per-order notional cap, daily order cap and emergency disable.
- Execution: Angel One orders remain explicitly gated; submitted order is not equivalent to a fill. Stop/target auto-square-off must not be assumed until an exit manager is implemented and tested.
- Operations: Railway HTTPS backend, health endpoint, server-side secret storage, diagnostics, audit/monitoring and alert hooks.
- UI design and repository references are available from the app's Trading Setup, API & Railway, and Repository Library sections.
