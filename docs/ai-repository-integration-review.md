# External AI/trading repository review for Fresh-Apk

Review date: 2026-10-09. This is a capability review, not a claim that third-party repositories or pretrained models have been vendored. The repeated Agentic-AI URL in the original request was deduplicated. The three GitHub topic URLs are discovery indexes, not individual codebases.

## Integration rule

Fresh-Apk remains an Angel One Indian-index F&O signal platform. Keep the current Flutter UI and backend boundaries; do not import entire applications, broker adapters, dependency trees, secrets, or incompatible data assumptions. Reimplement useful patterns against Fresh's normalized `MarketSnapshot`, retain source attribution, and inspect each upstream LICENSE before copying any code. Research ideas and algorithms are not the same as permission to copy source. Crypto/forex/US-equity examples are not directly valid for NSE index options without adaptation and tests.

## Repository review and capability mapping

| Source | Useful pattern observed | Fresh-Apk integration / disposition |
|---|---|---|
| [asavinov/intelligent-trading-bot](https://github.com/asavinov/intelligent-trading-bot) | Consistent feature engineering between offline training and online inference; multi-timeframe signals; model aggregation; backtesting. | Fresh already has deterministic indicators, confluence checks, a strategy pipeline and walk-forward validation. Preserve one shared feature contract for live/backtest; do not import crypto-specific configuration or claim ML models are trained. |
| [Sebacaraballo/Trading-Bot](https://github.com/Sebacaraballo/Trading-Bot) | SEC 8-K filing/news signal extraction, FastAPI service, dashboard and backtesting. | Adapt only the general event-evidence + replay idea. SEC filings are not a primary source for Indian index-option intraday decisions; no SEC-specific pipeline copied. |
| [qrak/LLM_trader](https://github.com/qrak/LLM_trader) | Paper-trading-first agent, outcome memory/reflection, chart reasoning and risk metrics. | Fresh has a paper-trade monitor and adaptive-intelligence diagnostics. Reflection remains explicitly unavailable until closed-trade history is supplied; chart vision is not claimed integrated. |
| [fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis](https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis) | Multi-source news/social ingestion, LLM specialist roles, hybrid rules + model review, risk controls and paper trading. | Fresh's specialist ensemble and OpenAI decision packet follow the same high-level pattern. This change adds sentiment source coverage/provenance diagnostics; no third-party code or broker execution is copied. |
| [ItsKillionaire/TradeSignalFlux](https://github.com/ItsKillionaire/TradeSignalFlux) | News-to-LLM analysis, deduplicated processed articles, provider keys outside source, alert-oriented recommendations. | Fresh already queries Exa, Tavily and Brave and deduplicates canonical URLs. The evidence report now surfaces provider/domain diversity and missing publication dates. No Telegram bot or DeepSeek dependency added. |
| [studiogangster/next-gen-algo-trading-bot](https://github.com/studiogangster/next-gen-algo-trading-bot) | Live/historical candle upsert, partitioned sync, cache-backed indicators and multi-timeframe charts. | Keep as architecture reference for live/historical consistency and stale-data diagnostics. Its Zerodha/Redis/Ray/Vue stack is not a drop-in replacement for Angel One + Flutter. |
| [FalconTrading06/llm-tradebot](https://github.com/FalconTrading06/llm-tradebot) | Candidate LLM-trading reference supplied by user. | Repository-specific source/license claims are not recorded until its files and license are inspected through GitHub; no source is represented as integrated from this link alone. |
| [DevGohil411/Trading-bot](https://github.com/DevGohil411/Trading-bot) | README describes a three-layer design: ML filter, LLM sentiment and risk engine; dynamic volatility-based sizing and dual targets. | Fresh has risk gates, an AI layer and target/risk planning. This is a design comparison, not evidence that a compatible trained ML filter has been imported. Any sizing remains blocked when lot-size/risk inputs are missing. |
| [Gifted87/TradingBot](https://github.com/Gifted87/TradingBot) | SMC/Wyckoff-style price structure, signal levels, and multi-agent technical analysis. | Fresh's existing price-action/trap/structure modules cover related concepts. Forex/crypto yfinance assumptions are not copied into NSE options. |
| [TradingGoose/TradingGoose.github.io](https://github.com/TradingGoose/TradingGoose.github.io) | Multi-agent workflow, event-driven research, portfolio/risk perspectives and orchestration. | Fresh already produces named specialist diagnostics. Portfolio agent reports unavailable unless account exposure is actually supplied; no autonomous order execution added. |
| [Open-Finance-Lab/FinLLM-Leaderboard trading-agent demo](https://github.com/Open-Finance-Lab/FinLLM-Leaderboard/blob/main/docs/source/demos_of_finagents/trading_agent.rst) | Separates news-derived LLM signals from financial RL strategies and describes distinct value, sentiment and risk-agent roles. | Use as an evaluation design reference. Do not claim FinRL is trained or connected; future model comparisons should be scored on out-of-sample, net-of-cost outcomes. |

### Discovery indexes

- [quantitative-finance topic](https://github.com/topics/quantitative-finance): broad directory; not one implementation to copy.
- [trade-analysis topic](https://github.com/topics/trade-analysis): broad directory; inspect individual repositories and licenses before selecting anything.
- [tradingbot2026 topic](https://github.com/topics/tradingbot2026): broad directory, including unrelated crypto bots; not treated as an integration source.

## Code change in this review

`backend/app/agent_ensemble.py` now reports:
- evidence count and usable-text count;
- distinct provider and domain counts;
- evidence with/without publication dates;
- a small positive/negative keyword tally labelled explicitly as a lexical hint, not a trained sentiment model;
- an explicit warning that sentiment is contextual and cannot override deterministic risk/data-quality gates.

Regression tests cover source diversity, missing publication dates, absent evidence, and a positive news hint being unable to clear a `STALE_DATA` hard block.

## Important boundaries still requiring separate validation

- Run backend tests and Android build CI after this commit; a GitHub commit alone does not prove tests or APK build passed.
- Validate live Angel One authentication, websocket/REST freshness, option-token discovery, and data population against a real configured session.
- Validate walk-forward backtests with chronological splits, no look-ahead, slippage, brokerage/taxes and option spread assumptions.
- Keep real order placement disabled unless separately reviewed, explicitly configured and human-confirmed.
