# Fresh Platform Architecture

## 1. Collection layer

`AngelGateway` owns the broker boundary. It is the only module that knows SmartAPI session details. Live ticks use SmartWebSocketV2; REST is used for login, snapshots, historical candles and account-readable portfolio/position data.

The instrument master is treated as a daily reference, not as live price data. The collector caches the last successful copy and never discards a known-good master solely because a refresh failed.

## 2. Normalization layer

Every market update is normalized into a provider-neutral structure with:

- index and exchange
- timestamp and age
- underlying LTP/OHLC/volume
- option strike, CE/PE, LTP, volume, OI and OI delta
- optional Greeks/IV
- source and confidence metadata

This prevents a broker SDK shape from leaking into the strategy engine.

## 3. Deterministic strategy layer

The strategy engine combines:

- trend: EMA 8/13 relationship and slope
- momentum: RSI 14 and MACD
- volatility: ATR 14 and IV when available
- volume/price context: VWAP
- derivatives: PCR and option OI/premium quadrants
- OI regimes: long buildup, short buildup, short covering, long unwinding
- conflicting-side override
- liquidity/staleness guard

A signal is a candidate, never a guaranteed trade. Entry/SL/target are derived from the selected option's market data and risk parameters.

## 4. Search evidence layer

The signal packet is enriched independently through three provider adapters: Exa, Tavily and Brave Search. A provider failure is isolated; it does not crash signal generation. Evidence is stamped with provider, title, URL and snippet so the AI prompt can separate market data from public-web context.

## 5. AI layer

Six layers are explicit contracts:

1. Data Quality AI — validates freshness/completeness.
2. Market Regime AI — trend, volatility and event context.
3. Technical AI — interprets the indicator packet.
4. Derivatives AI — interprets OI/premium/PCR/strike structure.
5. Risk AI — evaluates entry/SL/target and invalidation conditions.
6. Decision AI — returns CALL BUY / PUT BUY / WAIT / NO TRADE with reasons and risk flags.

OpenAI is called from the backend via the Responses API. Structured output is expected so downstream Flutter rendering remains deterministic.

## 6. Data freshness contract

- WebSocket ticks: target sub-second to a few seconds depending on broker feed and network.
- Option-chain/snapshot polling: configurable, default 15–30 seconds.
- Engine cycle: default 5 seconds over the latest cached data.
- Stale guard: default 15 seconds for live signal eligibility.
- If live data is unavailable, cached data can still be displayed, but the signal state becomes stale/no-trade instead of pretending it is live.

## 7. Account data

The platform can read positions and holdings through the authenticated broker session. A guarded Angel One LIMIT-order endpoint exists behind server configuration, fresh-data/risk validation and explicit human confirmation. Automatic stop-loss/target exit management is not complete; order submission does not prove a fill.

## 8. Deployment

Backend: Docker + Railway. Flutter: GitHub Actions Android build. Secrets: Railway environment variables or a future encrypted secret store. UI: direct backend URL, never direct broker/OpenAI calls from the APK.
