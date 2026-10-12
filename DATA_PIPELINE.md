# Fresh Data Pipeline

## Source of truth

The broker session is the source of truth for account and live market data. The web-search layer is context only; it must never override a broker price, option OI or timestamp.

## Collection sequence

1. Load/cache the Angel One instrument master.
2. Resolve the six tradeable indexes and the nearest active option expiry.
3. Subscribe to index + option tokens through SmartWebSocketV2.
4. Keep the latest tick for every subscribed token.
5. Sample current index prices into indicator history.
6. Build an option snapshot from the latest CE/PE ticks.
7. Calculate OI delta and premium delta against the previous sample.
8. Run deterministic indicators and OI regime classification.
9. Apply stale/missing/liquidity/conflict guards.
10. For a directional candidate, fan out the same signal packet to Exa, Tavily and Brave.
11. Combine evidence with the deterministic packet and send to the OpenAI decision layer.
12. Publish one structured signal object to Flutter.

## Refresh policy

- Tick store: event-driven.
- Strategy cycle: 5 seconds by default.
- Instrument master: refresh on startup/manual sync and keep cached last-good copy.
- AI enrichment: 30 seconds by default and only when a new directional fingerprint appears.
- Stale signal threshold: 15 seconds by default.

## Failure policy

| Failure | UI/result |
|---|---|
| Broker disconnected | NO TRADE / connection warning |
| Option-chain missing | NO TRADE |
| Data older than stale threshold | NO TRADE |
| One search provider fails | Continue with remaining evidence |
| All search providers fail | Deterministic signal remains visible; AI evidence count = 0 |
| OpenAI key absent | Deterministic signal is returned with AI_NOT_CONFIGURED |
| OpenAI request fails | Signal remains but AI enrichment is marked error |
| Instrument master refresh fails | Last cached master is used |
