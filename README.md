# Fresh Algo Signal Trading Platform

Fresh is an Android-first Indian index F&O market-intelligence and decision-support platform. The Flutter client connects to the FastAPI backend, which owns Angel One SmartAPI sessions, live WebSocket/REST market data, normalized snapshots, deterministic indicators/OI analysis, research confluence, OpenAI interpretation and risk validation.

## Current mobile workspace

1. Dashboard
2. Market
3. Option Chain
4. OI Lab
5. Indicators
6. Signals
7. Risk
8. Commodities
9. Backtesting
10. API
11. AI Access
12. Data Health
13. API & Railway
14. Repository Library
15. Trading Setup
16. Research Engines
17. 3-Layer Trade Engine
18. Broker Home (Prototype) — optional Groww-inspired layout backed only by existing Angel One market snapshots
19. PDF Report & Repositories — in-app guide covering all 10 report pages, all 15 screenshot captions, fix order, safety gates and repository links

The former Paper Trades tab has been removed from the APK navigation. Existing backend paper-monitor endpoints are retained for compatibility with earlier data; they are not presented as an app feature.

## Main capabilities

- Angel One SmartAPI login boundary and SmartWebSocketV2 / REST quotes.
- Index universe: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX and BANKEX.
- Option-chain snapshot with LTP, bid/ask, volume, OI, OI change, quote age and optional Greeks/IV when actually supplied.
- Deterministic EMA, RSI, MACD, ATR, VWAP, Bollinger, z-score, realized volatility plus OHLC-derived EMA50/200, stochastic, Williams %R, ROC, ADX, Supertrend direction and 20-bar support/resistance when sufficient candles exist.
- OI/premium quadrant classification and explicit unknown/missing-data handling.
- Three search connectors: Exa, Tavily and Brave Search; OpenAI analysis stays server-side.
- 3-layer workflow: signal candidate → deterministic risk/validation gate → gated execution/order-status monitoring.
- Historical Angel One index-candle replay for EMA crossover + ATR stops/targets, with next-bar-open entries, conservative stop/target collision handling and explicit cost assumptions.
- PDF Report & Repositories provides a page-by-page in-app transcription of the uploaded 10-page error report, its 15 screenshot captions, ordered troubleshooting checklist and repository/documentation links. It is a structured text companion, not an embedded pixel-identical PDF viewer.
- Broker Home (Prototype) is an additional, separate investing-app-style screen. It reads existing Angel One-backed market snapshots and introduces no Groww API, SDK, account, or credentials. Holdings are not fabricated when no verified portfolio endpoint is exposed.
- Research Engines tab displays current backend outputs; external repositories are research references, not represented as copied/installed code.
- Live Angel One order endpoint remains gated by server settings, fresh data, validation and explicit human confirmation. Automatic stop-loss/target exit management is not complete.

## Backtest scope (important)

The current historical replay is an **underlying-index spot proxy**, not an options-premium P&L backtest. It uses real Angel One index candles and does not claim to simulate historical option Greeks, changing strikes, expiry effects, bid/ask fills or historical option premiums. Use this mode to validate baseline signal timing only. A full option-premium backtest requires historical option contract candles and contract/expiry mapping for each simulated entry.

## Security

Broker credentials, OpenAI keys and search-provider keys belong at the backend boundary. Angel session tokens and remembered credentials are encrypted server-side using `APP_FERNET_KEY`; TOTP is not persisted. Never put secrets in the APK or commit them to Git.

## Data flow

```text
Angel One SmartAPI REST + WebSocket
  -> instrument master + normalized market store
  -> freshness/data-quality gate
  -> indicators + option-chain/OI + strategy confluence
  -> Exa + Tavily + Brave evidence
  -> OpenAI structured interpretation
  -> deterministic risk/validation gate
  -> signals / 3-layer engine / gated order status
```

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Run Flutter

```bash
cd flutter_app
flutter create --platforms=android .
flutter pub get
flutter run
```

GitHub Actions bootstraps the Android wrapper for release builds. Deploy the backend from the repository root on Railway and inject secrets through environment variables; never commit `.env` files.
