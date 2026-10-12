# Fresh-Apk Strategy, Pro Chart and Indian Index UI Integration

Branch: `fresh-platform-v1`

## Added to the Android app

- The existing **Market** tab now contains a native candlestick chart for the selected index, with 1m / 5m / 15m timeframes, OHLC candles, price grid and a last-close guide.
- The chart renders only backend-provided candle bars. If real/history candles are absent, it displays a waiting state; it does not create sample/synthetic prices.
- The Dashboard now uses a compact Indian F&O index board for NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX and BANKEX, with live-or-missing price, regime, decision and confidence.
- The existing **Indicators** tab now includes tappable links to strategy research, chart libraries and Indian-index dashboard examples. The app remains at ten top-level tabs.
- Added a widget regression test ensuring missing chart data is not fabricated.

## Strategy research links exposed in-app

- https://github.com/paperswithbacktest/awesome-systematic-trading
- https://github.com/joelowj/awesome-algorithmic-trading
- https://github.com/wilsonfreitas/awesome-quant
- https://github.com/cbailes/awesome-deep-trading
- https://github.com/topics/trading-strategies

## Pro chart references

- https://github.com/rudra-sah00/trading-chart
- https://github.com/klinecharts/KLineChart
- https://github.com/tradingview/lightweight-charts

## Indian index UI references

- https://github.com/vikram-2101/Stock-Market-Dashboard
- https://github.com/SujaySingh-0403/stock-dashboard
- https://github.com/DevMLAI01/stock-market-dashboard

## Important integration boundary

These projects are exposed as clickable research references; their source code has **not** been blindly copied into Fresh-Apk. The current chart is a lightweight native Flutter candlestick renderer using the app's existing normalized market payload, not the full TradingView/KLineChart library. The backend's deterministic strategy/risk gates remain the authority; a chart or repository link is not a trading signal and does not guarantee profitability.

## Verification still required

GitHub Actions must complete for the new commits. The chart requires genuine candle history from Angel One or the backend historical-candle warm-up. If the feed/history is absent, the UI intentionally shows no-data status. Validate on an actual Android device with a connected Angel One session before relying on it for market decisions.


## Expanded navigation and API/Railway hub

- Added a left-side hamburger drawer that navigates to all app sections; the horizontal tab bar remains available.
- Expanded the navigation to 13 sections by adding **Data Health**, **API & Railway**, and **Repository Library**. This intentionally exceeds the previous ten-tab preference at the user's request.
- **Data Health** surfaces the current backend, signal endpoint and Angel One status along with the returned feed/store diagnostic payloads and a refresh action.
- **API & Railway** opens Railway's FastAPI template, template catalog, GitHub deployment page, dashboard, docs, CLI guide, FastAPI docs, and the current Fresh-Apk branch. It explains HTTPS health checks and server-side secret handling.
- **Repository Library** lists the strategy, chart and Indian-market UI repositories in-app. Links are references; upstream code is not automatically copied or integrated just by listing it.
- The repository link launcher uses Android external-browser launch via `url_launcher`.


## Complete Trading Setup — Angel One edition

Added a **Trading Setup** section to the app's left hamburger menu. Navigation now contains 14 sections, including Data Health, API & Railway, Repository Library and Trading Setup.

The new setup guide groups source references and operational design into:
1. Angel One SmartAPI broker/data integration (no Zerodha/Kite dependency)
2. Strategy and signal engine
3. Signal quality/evidence filter
4. Backtesting and walk-forward validation
5. Risk and trade management
6. Paper trading and explicitly gated broker execution
7. Monitoring, alerts and audit
8. Charts, dashboard and mobile UX
9. FastAPI/Railway backend, secrets and deployment

The screen presents the architecture:
Angel One REST/WebSocket → freshness/data-quality gate → normalized market store → indicators/OI engine → AI/search evidence → signal scoring → backtest/paper validation → risk limits → optional gated Angel One order → order/fill/position monitor → dashboard/alerts.

Third-party links are research references only. The app does not claim to have copied, installed or verified the compatibility of every linked repository. Before using third-party components, review licensing, security, Indian broker/exchange rules, and API assumptions. The current backend's live execution remains separately gated; this guide does not enable live trading.
