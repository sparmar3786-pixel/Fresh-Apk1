# Research-source integration for Fresh Algo Signal

## What is included

Fresh keeps its Angel One data adapter, normalized market snapshot, current indicator/OI engine, stale-data guard, live AI validation and risk controls. This branch adds an original, dependency-light research pack for:
- trend following using EMA direction plus MACD histogram agreement;
- mean-reversion *watch* conditions requiring both RSI and price z-score extremes;
- option premium/OI classification (long buildup, short buildup, short covering, long unwinding);
- quote-spread liquidity diagnostics when a valid bid/ask/LTP is actually available.

The pack is diagnostic and is surfaced through the strategy confluence payload. It does not place orders, invent missing fields, or override existing live-data, risk, or AI-validation gates. Its score is not a win probability. HFT replay, queue-position, and latency modelling require suitable full-depth tick/order-book data and are not claimed by this lightweight module.

## Requested upstream repositories

1. [wangzhe3224/awesome-systematic-trading](https://github.com/wangzhe3224/awesome-systematic-trading) — MIT-licensed curated research list. Useful as a discovery catalogue, not a single executable strategy engine.
2. [paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) — curated list of libraries, strategies and research papers. The repository does not expose a root LICENSE file on the inspected branch; do not bulk-republish its catalogue/content until its terms are verified.
3. [georgezouq/awesome-ai-in-finance](https://github.com/georgezouq/awesome-ai-in-finance) — CC0 catalogue of AI/finance projects, papers, tools and strategies; listed projects keep their own licenses.
4. [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) — MIT-licensed HFT backtesting framework with Python/Numba and Rust components. It is not embedded in the Android APK: its native toolchain, dependencies and required full-depth data make that a separate backend research integration.
5. [ranaroussi/qtpylib](https://github.com/ranaroussi/qtpylib) — Apache-2.0 licensed indicator/trading library, archived by its maintainer in January 2024 and designed around Interactive Brokers. Fresh does not copy its broker-specific runtime or dependencies into the APK.

## Why this is not a byte-for-byte bundle

Two repositories are curated link/catalogue collections rather than a single package to import. The other projects have separate runtimes, dependencies and broker/data assumptions. Placing entire source trees inside an APK would not make their strategies execute against Angel One and would increase size and licensing/dependency risk. Fresh instead documents all five sources and implements compatible, original strategy logic in its backend; upstream project code is not falsely represented as ported.

## Verification required before live use

- Run backend tests and Android APK workflow.
- Test on replay/paper data with realistic fees, slippage and missing-data cases.
- Compare against out-of-sample/walk-forward periods and a no-trade baseline.
- Verify live Angel One data freshness and option-chain completeness.
- Keep real order placement behind the existing risk and AI validation gates.


## Additional AI/agent research audit

The following links were inspected as architecture/feature references. Fresh uses a single configured OpenAI API for language-model synthesis; the roles below are lightweight specialist reports over the same Angel One snapshot, not separate paid LLM providers. No upstream source trees, weights, datasets, secrets, broker adapters or copied executable code are bundled.

- [asavinov/intelligent-trading-bot](https://github.com/asavinov/intelligent-trading-bot) (MIT): feature parity between offline training and live inference, multi-timeframe signals, model evaluation. Fresh does not claim a trained predictor without a trained artifact.
- [Sebacaraballo/Trading-Bot](https://github.com/Sebacaraballo/Trading-Bot) (MIT): structured LLM extraction, explicit risk flags, and backtest statistics. Its SEC 8-K equity workflow is not directly interchangeable with Indian index options.
- [qrak/LLM_trader](https://github.com/qrak/LLM_trader) (MIT): claim validation, reflection/memory, risk gates and fallback concepts. Fresh reports reflection unavailable until closed-trade outcomes are actually supplied; its multi-provider routing and crypto/RAG runtime are not copied.
- [fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis](https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis): news/social sentiment + ML + LLM roles. No verified sentiment feed is connected in Fresh after the search integrations were removed, so sentiment is explicitly UNAVAILABLE rather than fabricated. No root license was exposed in the metadata audit; do not copy its source until licensing is confirmed.
- [ItsKillionaire/TradeSignalFlux](https://github.com/ItsKillionaire/TradeSignalFlux): news-sentiment recommendation concept; Fresh does not claim a live news feed from this reference.
- [studiogangster/next-gen-algo-trading-bot](https://github.com/studiogangster/next-gen-algo-trading-bot): indicator/timeframe pipeline and broker separation. Its Zerodha Kite adapter and execution runtime are not copied into the Angel One app.
- [FalconTrading06/llm-tradebot](https://github.com/FalconTrading06/llm-tradebot) (MIT): specialized data, quant, prediction, decision and risk agents. Fresh exposes corresponding diagnostic roles; it does not claim those agents are separate trained models.
- [DevGohil411/Trading-bot](https://github.com/DevGohil411/Trading-bot): includes MT5/XAUUSD-specific strategies and bundled runtime/artifacts; Fresh does not import its broker-specific code, binary models, database or secrets. License was not exposed in the metadata audit.
- [Gifted87/TradingBot](https://github.com/Gifted87/TradingBot): multi-agent FX analysis concept. No source code is copied; no root license was exposed in the metadata audit.
- [TradingGoose/TradingGoose.github.io](https://github.com/TradingGoose/TradingGoose.github.io) (AGPL-3.0): event-driven analysis and a portfolio-manager role. Fresh adapts the role separation concept only; no AGPL code is copied.
- [Open-Finance-Lab/FinLLM-Leaderboard](https://github.com/Open-Finance-Lab/FinLLM-Leaderboard): benchmark/dataset catalogue and demo agent patterns, not a drop-in live Angel One engine. Benchmark files and model weights are not copied.
- [quantitative-finance topic](https://github.com/topics/quantitative-finance), [trade-analysis topic](https://github.com/topics/trade-analysis), and [tradingbot2026 topic](https://github.com/topics/tradingbot2026) are GitHub topic pages, not single repositories; the same fsaavedra repository appeared three times in the request and is audited once.

### What was added to Fresh

- A transparent specialist report for market regime, deterministic quant/technical indicators, option premium/OI flow, sentiment availability, risk audit, reflection-history availability, and portfolio-context availability.
- The specialist report is attached to the OpenAI market brief. It does not add more external AI providers or bypass deterministic no-trade gates.
- Unknown sources remain UNKNOWN/UNAVAILABLE; no claim is made that a model has been trained or that sentiment has been fetched if the feed is absent.
- Source licensing and runtime constraints are recorded here; this is a functional adaptation, not a byte-for-byte repository bundle.

### Agentic AI integration update

The current branch now sends the deterministic specialist packet to the configured OpenAI decision call and asks for structured specialist reviews for:

- market regime / scenario analyst;
- quant and technical analyst;
- options-flow analyst (OI + premium classifications);
- sentiment analyst (must stay UNAVAILABLE until verified news/social evidence is supplied);
- risk auditor (hard guards override model opinion);
- reflection analyst (must stay UNAVAILABLE until closed-trade history is supplied);
- portfolio manager (must stay UNAVAILABLE until positions, equity and exposure limits are supplied);
- final reviewer (alignment, contradictions and invalidation conditions).

The Signal screen displays each specialist's status, view, rationale and risk flags. These are roles in **one configured OpenAI call**, not eight independent models, and the role names do not imply separately trained ML agents. This keeps the earlier removal of Exa/Tavily/Brave intact. No source-code subtree, model weight, or third-party secret is copied into Fresh. MIT/Apache material can be reused only with its license/notice requirements; the TradingGoose AGPL-3.0 implementation is not copied, and repositories with no verified license are used only as high-level design references.

Automated tests cover unavailable-source enforcement and the rule that hard risk guards override an LLM-proposed clear verdict. A successful CI run still does not prove that the live Angel One feed, sentiment ingestion, model training, or trading profitability has been verified.
