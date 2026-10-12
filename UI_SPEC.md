# Fresh UI Specification

The Android client keeps the existing Fresh dark theme and adds focused screens without redesigning the existing layout. The former Paper Trades tab has been removed. The current navigation has 17 tabs.

| Tab | Purpose | Data / behavior |
|---|---|---|
| Dashboard | Cross-index pulse and connectivity | Latest API snapshot, six indexes |
| Market | Underlying price, trend and regime | Selected index snapshot |
| Option Chain | Sortable pro quote table with CE/PE filter | Up to 60 closest returned option quotes, optional Greeks and freshness |
| OI Lab | PCR, OI deltas and OI regime | Current option-chain snapshot |
| Indicators | Technical indicators and editable EMA periods | Live strategy output; advanced OHLC indicators show N/A until history exists |
| Signals | CALL BUY / PUT BUY / WAIT / NO TRADE with entry/SL/targets and validation | Strategy + AI + deterministic risk gate |
| Risk | Risk checks and qualified plans | Current signal |
| Commodities | Instrument quotes and feed status | Returned MCX snapshots |
| Backtesting | Configurable historical candle replay | Authenticated Angel One historical index candles |
| API | Backend and broker connection settings | HTTPS backend configuration |
| AI Access | OpenAI and search-provider keys | Server-side AI settings |
| Data Health | Backend/session status and per-index freshness | No raw feed/store diagnostic cards |
| API & Railway | Deployment and secret-management guidance | Reference links and checklist |
| Repository Library | Existing external references and current engine output | Links are references, not proof of integration |
| Trading Setup | Nine live setup checks plus repository references | Backend, Angel session, data, strategy, OI, validation, backtest, AI and execution |
| Research Engines | Live indicators/OI/confluence/validation plus non-chart research references | Actual current backend output; no invented data |
| 3-Layer Trade Engine | Signal → risk validation → gated execution status | Existing backend validation; no automatic order placement from this screen |

## Signal safety

- A strategy candidate is not automatically an actionable trade.
- Stale or incomplete market/option data must not be labeled live.
- AI confidence is not a probability of profit.
- Missing Greeks/IV/OI values remain unavailable rather than being invented.
- The historical backtest is explicitly an index-spot proxy, not historical option-premium P&L.
- Live order placement remains separately gated and requires human confirmation.

## Visual language

- Keep the current Fresh dark theme.
- Green for positive/bullish, red for negative/bearish, amber for warning/unknown.
- Dense but readable phone-sized cards.
- The pro option-chain table may scroll horizontally for full quote fields.
- Groww-inspired layout is limited to new card hierarchy; Groww branding/assets are not copied.
