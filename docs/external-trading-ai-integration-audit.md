# External Trading-AI Repository Integration Audit

Target: `fresh-platform-v1`  
Date: 2026-10-09  
Status: repository review started; **no upstream source has been wholesale copied**.

## Integration policy

Fresh-Apk is an India F&O market-intelligence app using Angel One data. Upstream projects are references, not drop-in modules. Port only isolated, license-compatible ideas after reviewing their actual source, dependencies, tests, and security implications. Do not import foreign broker execution, crypto/forex assumptions, secrets, or whole dashboards into the mobile app. Preserve the read-only / human-confirmed execution boundary and data-quality gate.

## Repositories reviewed at README level

| Source | Reusable idea to investigate | Adaptation / caution |
|---|---|---|
| https://github.com/asavinov/intelligent-trading-bot | Separate offline model training from online inference; consistent feature engineering; backtesting and multiple time rasters | Reuse feature-contract and evaluation concepts; inspect license and implementation before porting |
| https://github.com/Sebacaraballo/Trading-Bot | LLM extraction into structured sentiment, confidence, bull/bear cases and risk flags; filing/news evidence; benchmarked backtests | Convert to an optional event/news evidence adapter; US SEC equities are not Indian index-option signals |
| https://github.com/qrak/LLM_trader | Outcome memory, semantic retrieval, chart/context analysis, paper-trading-first | Consider an auditable signal/outcome journal and retrieval over past setups; do not import a separate autonomous executor |
| https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis | Multi-source news/social/document ingestion; hybrid rules + ML + LLM reasoning; monitoring and paper trading | Add evidence provenance and sentiment as a secondary feature only; external-source freshness and hallucination guards required |
| https://github.com/ItsKillionaire/TradeSignalFlux | News deduplication, retry/error handling, structured sentiment/risk assessment, notification patterns | Adapt idempotency and retry patterns; Telegram/news provider is not a replacement for broker market data |
| https://github.com/studiogangster/next-gen-algo-trading-bot | Per-instrument data workers, real-time + historical candle reconciliation, multi-timeframe charts, cache/upsert | Strong candidate for feed reliability and candle-gap tests; its Zerodha integration is not Angel One compatible as-is |
| https://github.com/FalconTrading06/llm-tradebot | Market-regime-first decisioning, multiple specialist agents, central decision core, calibrated scores and risk audits | Consider agent contracts and veto/audit stage; validate any performance claims independently |
| https://github.com/DevGohil411/Trading-bot | ML filtering, LLM sentiment and risk engine, dynamic volatility-aware risk, multi-target setup | Evaluate concepts only; MetaTrader 5 assumptions do not transfer directly to NSE options |
| https://github.com/Gifted87/TradingBot | Smart Money Concepts and Wyckoff analysis | Optional, testable structure features; current README focuses on forex/crypto and should not be copied as an NSE strategy |
| https://github.com/TradingGoose/TradingGoose.github.io | Multi-agent workflow, analytics, charting, monitoring and workflow automation | Study orchestration boundaries; source points to the separate TradingGoose-Studio repository |
| https://github.com/Open-Finance-Lab/FinLLM-Leaderboard/blob/main/docs/source/demos_of_finagents/trading_agent.rst | Financial-LLM agent evaluation / benchmarking patterns | Use as evaluation research, not as a live trading engine |
| https://github.com/topics/quantitative-finance | Discovery list for quantitative-finance tools | Topic page is not a single implementation; candidates must be individually assessed |
| https://github.com/topics/trade-analysis | Discovery list for trade-analysis tools | Topic page is not a single implementation; candidates must be individually assessed |
| https://github.com/topics/tradingbot2026 | Discovery list for trading-bot projects | Topic page is not a single implementation; candidates must be individually assessed |

The three repeated links to the fsaavedra0003 repository are deduplicated; each unique repository is reviewed once.

## Proposed Fresh-Apk integration sequence

1. **Repair/verify live data first:** health endpoint, Angel One auth/TOTP, instrument master, WebSocket subscription, REST quote fallback, normalized timestamps, per-index last-update/error status, option-chain/OI availability. Never fabricate data when a provider is unavailable.
2. **Feature contract:** one normalized, timestamped feature packet per index/timeframe, including EMA 8/13, RSI, MACD, VWAP, ATR, candles, OI change, PCR, buildup/unwinding classification, option spread/volume and missing-data flags.
3. **Deterministic gates:** freshness and completeness → market regime → technical/derivatives confluence → opposite-side conflict check → risk/reward and liquidity checks → WAIT/NO TRADE fallback. LLM must not override hard data/risk vetoes.
4. **Evidence-based AI:** structured JSON schema with decision, reasons, counter-evidence, confidence, risk flags, source timestamps, missing inputs and invalidation conditions. Keep news sentiment separate from price/OI evidence and deduplicate source articles.
5. **Evaluation:** walk-forward splits, leakage prevention, realistic slippage/fees, out-of-sample metrics, regime slices, calibration, and paper-trading logs. No strategy is assumed profitable without measured results.
6. **Operational hardening:** idempotent retries, rate-limit/backoff, bounded timeouts, circuit breakers, provider health, traceable errors and per-page freshness indicators.
7. **Compatibility gate:** review each source's license, exact files/dependencies, security, tests and API contracts before copying code. Port small modules with attribution and isolated tests; do not merge entire projects wholesale.

## Implementation updates on `fresh-platform-v1`

The following Fresh-Apk-native implementation has now been committed:

- `backend/app/search_evidence.py`: original multi-provider adapter for Exa, Tavily and Brave News; bounded result counts/timeouts; provider failures degrade to partial evidence; HTTP(S)-only URLs; URL tracking-query/fragment removal for deduplication.
- `backend/app/secure_store.py`: encrypted per-device storage/load for all three search keys; blank fields preserve previously saved values rather than wiping the other provider credentials.
- `backend/app/config.py`: optional server environment variables for all search keys.
- `backend/app/main.py`: sends index-specific news evidence into the existing OpenAI/agent analysis; adds `POST /v1/providers/search/test`; returns provider configuration status without returning secrets.
- `backend/app/ai.py`: treats external news as untrusted evidence, requires source attribution when used, and prevents sentiment from overriding hard data/risk gates.
- `flutter_app/lib/main.dart` and `flutter_app/lib/api.dart`: AI Access screen fields for Exa, Tavily and Brave plus a provider test action.
- `tests/test_search_evidence.py`: tests provider configuration, URL normalization, query bounds and no-key behavior.

These are **Fresh-Apk-native adapters and UI changes inspired by architecture patterns**, not wholesale copies of upstream repositories. Reviewed source pages include the linked READMEs for the main candidate projects and license files where available. Several projects' licenses were not found at the expected root path; do not copy their code unless the actual license is located and reviewed. The topic pages are discovery indexes, not code repositories.

## Validation status

GitHub confirms the above file commits on `fresh-platform-v1`. A local clone could not be obtained in this environment, and no successful Android build or backend test-run result is available in this session. Therefore the code is committed but **runtime validation, provider-key tests against real services, GitHub Actions test completion, APK build and live Angel One data verification remain unconfirmed**. No provider key has been supplied or tested here.
