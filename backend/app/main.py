from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .ai import OpenAIDecisionEngine
from .angel import AngelGateway
from .config import settings
from .deps import require_device_id
from .instrument_master import InstrumentMaster
from .models import AIDecision, MarketSnapshot, StrategyResult, TradeDecision
from .obi import OBIEngine
from .live_execution import LiveExecutionError, LiveExecutionService, LIVE_CONFIRMATION
from .search_evidence import SearchEvidenceService
from .research_strategy_pack import evaluate_research_pack
from .secure_store import (
    angel_session_status,
    load_angel_session,
    init_store,
    load_ai,
    save_ai,
    save_angel_session,
    delete_angel_session,
    load_market_snapshots,
    save_market_snapshots,
)
from .signal_runtime import SignalRuntime
from .live_validation import validate_live_candidate
from .strategies import analyze, build_qualified_trade_plans
from backend.backtest.paper_monitor import PaperTradeMonitor
from backend.pipeline.adaptive_intelligence import evaluate_adaptive_intelligence
from .agent_ensemble import build_agent_ensemble
from backend.backtest.validation import evaluate_readiness, walk_forward_report
from backend.backtest.historical import run_ema_atr_backtest


class CredentialPayload(BaseModel):
    angel_api_key: str | None = None
    angel_client_code: str | None = None
    angel_pin: str | None = None
    angel_totp: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    exa_api_key: str | None = None
    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None


class AiCredentialsPayload(BaseModel):
    openai_api_key: str | None = None
    openai_model: str | None = None
    exa_api_key: str | None = None
    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None


class AngelConnectPayload(BaseModel):
    angel_api_key: str | None = None
    angel_client_code: str | None = None
    angel_pin: str | None = None
    angel_totp: str | None = None
    remember_credentials: bool = True


class AnalysisRequest(BaseModel):
    snapshot: MarketSnapshot
    news_query: str | None = None


class AIChatRequest(BaseModel):
    question: str
    index: str = "NIFTY"
    history: list[dict] = []


class StreamRequest(BaseModel):
    indexes: list[str] | None = None


class BacktestRequest(BaseModel):
    trades: list[dict] = []
    folds: int = 5
    slippage_r: float = 0.02
    transaction_cost_r: float = 0.02

class HistoricalBacktestRequest(BaseModel):
    index: str
    from_date: str
    to_date: str
    interval: str = "FIVE_MINUTE"
    fast_ema: int = 8
    slow_ema: int = 13
    atr_period: int = 14
    stop_atr: float = 1.5
    target_r: float = 2.0
    max_hold_bars: int = 30
    slippage_r: float = 0.02
    transaction_cost_r: float = 0.02


class PaperOpenPayload(BaseModel):
    trade_id: str
    strategy_id: str
    index: str
    side: str
    regime: str
    slippage_r: float = 0.0
    transaction_cost_r: float = 0.0
    notes: str = ""


class PaperClosePayload(BaseModel):
    gross_r: float
    notes: str = ""


class LiveOrderRequest(BaseModel):
    index: str
    lots: int = 1
    confirmation: str
    request_id: str


class RuntimeState:
    def __init__(self) -> None:
        self.angel = AngelGateway()
        self.obi = OBIEngine()
        self.live_execution = LiveExecutionService()
        self.master = InstrumentMaster()
        self.credentials = CredentialPayload(
            angel_api_key=settings.angel_api_key,
            angel_client_code=settings.angel_client_code,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            exa_api_key=settings.exa_api_key,
            tavily_api_key=settings.tavily_api_key,
            brave_search_api_key=settings.brave_search_api_key,
        )
        self.signals = SignalRuntime(
            self.master,
            self.angel.market_store,
            stale_after_seconds=settings.stale_data_seconds,
        )
        self.ai_latest: dict[str, AIDecision] = {}
        self.ai_keys: dict[str, str] = {}
        self.paper_monitors: dict[str, PaperTradeMonitor] = {}
        self.last_cycle = datetime.now(timezone.utc)
        self.last_rest_quote_poll_at: float = 0.0
        self.last_rest_option_cursor: int = 0

    def paper_monitor(self, device_id: str) -> PaperTradeMonitor:
        if device_id not in self.paper_monitors:
            data_dir = Path(os.getenv("DATA_DIR", "/tmp/fresh-algo-data"))
            safe_id = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:24]
            self.paper_monitors[device_id] = PaperTradeMonitor(
                storage_path=str(data_dir / ("paper_" + safe_id + ".sqlite3"))
            )
        return self.paper_monitors[device_id]

    def apply_ai(self, values: dict | None) -> None:
        if not values:
            return
        current = self.credentials.model_dump()
        for key in (
            "openai_api_key",
            "openai_model",
            "exa_api_key",
            "tavily_api_key",
            "brave_search_api_key",
        ):
            if values.get(key) is not None:
                current[key] = values[key]
        self.credentials = CredentialPayload(**current)

    def ai(self) -> OpenAIDecisionEngine:
        """Existing OpenAI engine retained for non-Signals flows."""
        return OpenAIDecisionEngine(
            self.credentials.openai_api_key,
            self.credentials.openai_model or settings.openai_model,
        )

    def signal_ai(self) -> OpenAIDecisionEngine:
        """Signals-only OpenRouter engine; never used by the AI Chat endpoint."""
        return OpenAIDecisionEngine(
            settings.openrouter_api_key,
            settings.openrouter_model,
            provider="openrouter",
        )


state = RuntimeState()


def build_subscription_groups(indexes_to_watch: list[str]) -> list[dict]:
    """Subscribe every requested index plus a balanced option slice per index."""
    groups: dict[str, set[str]] = {}
    exchange_map = {"NSE": "1", "NFO": "2", "BSE": "3", "BFO": "4", "MCX": "5"}

    for index in indexes_to_watch:
        row = state.master.find_index(index)
        if row:
            exchange_type = exchange_map.get(str(row.get("exch_seg", "")).upper())
            if exchange_type:
                groups.setdefault(exchange_type, set()).add(str(row["token"]))

        option_rows = state.master.option_rows(index)
        # Prefer the nearest non-expired expiry, then subscribe strikes nearest to
        # the current spot. This avoids spending the WebSocket budget on far expiries.
        def expiry_date(item: dict):
            raw_expiry = str(item.get("expiry", "")).strip()
            for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw_expiry.title(), fmt).date()
                except ValueError:
                    continue
            return None

        today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        dated_rows = [(expiry_date(item), item) for item in option_rows]
        valid_dated = [(expiry, item) for expiry, item in dated_rows if expiry is not None and expiry >= today_ist]
        if valid_dated:
            nearest_expiry = min(expiry for expiry, _ in valid_dated)
            option_rows = [item for expiry, item in valid_dated if expiry == nearest_expiry]

        spot = 0.0
        if row:
            spot_tick = state.angel.market_store.get(str(row.get("token", "")))
            raw_spot = (spot_tick or {}).get("last_traded_price", (spot_tick or {}).get("ltp", 0))
            try:
                spot = float(raw_spot or 0)
                if spot > 100000:
                    spot /= 100.0
            except (TypeError, ValueError):
                spot = 0.0

        def strike_value(item: dict) -> float:
            try:
                strike = float(str(item.get("strike", "0")) or 0)
            except (TypeError, ValueError):
                return 0.0
            return strike / 100.0 if strike >= 100000 else strike

        if spot > 0:
            options = sorted(
                option_rows,
                key=lambda item: (
                    abs(strike_value(item) - spot),
                    0 if str(item.get("symbol", "")).upper().endswith("CE") else 1,
                ),
            )[:100]
        else:
            # Before the first index tick, the median strike of the nearest expiry
            # is the safest available subscription center; refresh uses the live spot.
            options = sorted(
                option_rows,
                key=lambda item: (strike_value(item), str(item.get("symbol", ""))),
            )
            if len(options) > 100:
                middle = len(options) // 2
                options = options[max(0, middle - 50):max(0, middle - 50) + 100]

        for option in options:
            exchange_type = exchange_map.get(str(option.get("exch_seg", "")).upper())
            if exchange_type:
                groups.setdefault(exchange_type, set()).add(str(option["token"]))

    # Subscribe the nearest active MCX futures contracts alongside index F&O.
    for commodity in state.master.commodity_rows():
        if str(commodity.get("exch_seg", "")).upper() == "MCX" and commodity.get("token"):
            groups.setdefault("5", set()).add(str(commodity["token"]))

    return [{"exchangeType": int(k), "tokens": sorted(v)} for k, v in groups.items() if v]


async def warmup_historical_timeframes(indexes: list[str]) -> None:
    if not state.angel.authenticated:
        return
    # SmartAPI historical candle timestamps are exchange-local (India), not UTC.
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    fromdate = (now - timedelta(days=5)).strftime("%Y-%m-%d 09:00")
    todate = now.strftime("%Y-%m-%d %H:%M")
    for index in indexes:
        if not state.signals.needs_historical(index):
            continue
        row = state.master.find_index(index)
        if not row:
            continue
        exchange = str(row.get("exch_seg", "NSE")).upper()
        token = str(row.get("token", ""))
        if not token:
            continue
        try:
            candles = await asyncio.to_thread(
                state.angel.historical_candles,
                exchange=exchange,
                token=token,
                interval="ONE_MINUTE",
                fromdate=fromdate,
                todate=todate,
            )
            state.signals.seed_from_historical(index, "1m", candles)
        except Exception as exc:
            state.angel.last_error = f"{index} historical warm-up failed: {exc}"

async def ensure_live_feed(indexes: list[str] | None = None) -> dict:
    """Prepare instruments and start the authenticated stream without blocking login."""
    if not state.angel.authenticated:
        raise RuntimeError("Angel One session is not authenticated")
    if not state.master.rows:
        if not state.master.load_cache():
            await state.master.sync()
    indexes_to_watch = [x.upper() for x in (indexes or list(AngelGateway.INDEXES.keys()))]
    token_list = build_subscription_groups(indexes_to_watch)
    total = sum(len(group.get("tokens", [])) for group in token_list)
    if not token_list:
        raise RuntimeError("No instrument tokens found. Sync the Angel One instrument master.")
    if total > 950:
        raise RuntimeError(f"Subscription set too large: {total}; narrow the index/option universe.")
    state.signals.indexes = indexes_to_watch
    if state.angel.stream_needs_restart(settings.stale_data_seconds):
        state.angel.start_stream(token_list, on_tick=state.obi.on_tick)
    return {"indexes": indexes_to_watch, "subscriptions": total, "groups": token_list}


async def poll_rest_index_quotes(indexes: list[str]) -> None:
    """Rate-limited REST fallback for stale index and near-ATM option quotes.

    SmartAPI market-data requests accept at most 50 symbols. Underlyings are
    prioritized, then a rotating near-ATM option batch fills the remaining slots.
    This fallback never claims a quote is live unless its local receive time is fresh.
    """
    if not state.angel.authenticated or not state.master.rows:
        return
    now = time.time()
    if now - state.last_rest_quote_poll_at < 2.0:
        return
    state.last_rest_quote_poll_at = now

    exchange_tokens: dict[str, list[str]] = {"NSE": [], "BSE": [], "NFO": [], "BFO": [], "MCX": []}
    selected_tokens: set[str] = set()
    for index in indexes:
        row = state.master.find_index(index)
        if not row:
            continue
        exchange = str(row.get("exch_seg", "NSE")).upper()
        token = str(row.get("token", "")).strip()
        if exchange not in exchange_tokens or not token:
            continue
        current = state.angel.market_store.get(token)
        received_at = float(current.get("received_at", 0)) if current else 0.0
        if not current or now - received_at > settings.stale_data_seconds:
            exchange_tokens[exchange].append(token)
            selected_tokens.add(token)

    # Prioritize one nearest-expiry futures quote for each supported MCX commodity.
    for commodity in state.master.commodity_rows():
        exchange = str(commodity.get("exch_seg", "")).upper()
        token = str(commodity.get("token", "")).strip()
        if exchange == "MCX" and token and token not in selected_tokens and len(selected_tokens) < 45:
            exchange_tokens["MCX"].append(token)
            selected_tokens.add(token)

    # Build a small, near-the-money option universe for each index. The cursor
    # rotates through it across calls, so all six index chains get coverage.
    candidates: list[tuple[str, str]] = []
    for index in indexes:
        underlying = state.master.find_index(index)
        if not underlying:
            continue
        underlying_tick = state.angel.market_store.get(str(underlying.get("token", "")))
        try:
            underlying_ltp = float((underlying_tick or {}).get("last_traded_price") or (underlying_tick or {}).get("ltp") or 0)
            if underlying_ltp > 100000:
                underlying_ltp /= 100.0
        except (TypeError, ValueError):
            underlying_ltp = 0.0
        options = state.master.option_rows(index)
        def option_strike(option: dict) -> float:
            try:
                strike = float(option.get("strike") or 0)
                return strike / 100.0 if strike >= 100000 else strike
            except (TypeError, ValueError):
                return 0.0
        options.sort(key=lambda option: (
            abs(option_strike(option) - underlying_ltp) if underlying_ltp > 0 else 0.0,
            str(option.get("symbol", "")),
        ))
        for option in options[:12]:
            exchange = str(option.get("exch_seg", "")).upper()
            token = str(option.get("token", "")).strip()
            if exchange not in exchange_tokens or not token:
                continue
            current = state.angel.market_store.get(token)
            received_at = float(current.get("received_at", 0)) if current else 0.0
            if (not current or now - received_at > settings.stale_data_seconds) and token not in selected_tokens:
                candidates.append((exchange, token))

    remaining = max(0, 50 - len(selected_tokens))
    if candidates and remaining:
        cursor = state.last_rest_option_cursor % len(candidates)
        rotated = candidates[cursor:] + candidates[:cursor]
        chosen = rotated[:remaining]
        state.last_rest_option_cursor = (cursor + len(chosen)) % len(candidates)
        for exchange, token in chosen:
            exchange_tokens[exchange].append(token)
            selected_tokens.add(token)

    exchange_tokens = {
        exchange: sorted(set(tokens))
        for exchange, tokens in exchange_tokens.items()
        if tokens
    }
    if not exchange_tokens:
        return
    if sum(len(tokens) for tokens in exchange_tokens.values()) > 50:
        state.angel.last_error = "REST fallback safety limit exceeded; skipped quote batch."
        return
    try:
        response = await asyncio.to_thread(state.angel.market_data_multi, exchange_tokens, "FULL")
        if response.get("status") is False:
            state.angel.last_error = "REST quote rejected: " + str(response.get("message") or "SmartAPI returned status=false")
            return
        data = response.get("data") or {}
        fetched = data.get("fetched") or []
        for quote in fetched:
            if not isinstance(quote, dict):
                continue
            token = str(quote.get("symbolToken") or quote.get("symboltoken") or "")
            try:
                price = float(quote.get("ltp") or quote.get("last_traded_price") or 0)
                oi = float(quote.get("opnInterest") or quote.get("openInterest") or quote.get("open_interest") or quote.get("oi") or 0)
                volume = float(quote.get("tradeVolume") or quote.get("volume") or quote.get("volume_trade_for_the_day") or 0)
            except (TypeError, ValueError):
                continue
            if not token or price <= 0:
                continue
            normalized: dict[str, object] = {
                "token": token,
                "last_traded_price": price,
                "open_interest": oi,
                "volume_trade_for_the_day": volume,
                "source": "angel-one-rest-fallback",
                "timestamp": time.time(),
            }
            depth = quote.get("best5") or quote.get("depth") or {}
            if isinstance(depth, dict):
                buys = depth.get("buy") or depth.get("best_5_buy_data") or []
                sells = depth.get("sell") or depth.get("best_5_sell_data") or []
                for field, rows in (("best_bid", buys), ("best_ask", sells)):
                    if rows and isinstance(rows[0], dict):
                        try:
                            depth_price = float(rows[0].get("price") or 0)
                            normalized[field] = depth_price / 100.0 if depth_price > 100000 else depth_price
                        except (TypeError, ValueError):
                            pass
            state.angel.market_store.update(normalized)
        unfetched = data.get("unfetched") or []
        if unfetched:
            state.angel.last_error = "REST quote unfetched tokens: " + ", ".join(
                str(item.get("symbolToken") or item.get("symboltoken") or item.get("message") or "unknown")
                for item in unfetched[:5] if isinstance(item, dict)
            )
        elif fetched:
            state.angel.last_error = None
    except Exception as exc:
        state.angel.last_error = "REST market quote fallback failed: " + str(exc)


def restore_device_angel(device_id: str) -> bool:
    if state.angel.authenticated:
        return True
    # Do not resurrect the same persisted JWT after SmartAPI explicitly rejected
    # it. A fresh interactive login (current TOTP) is required.
    if state.angel.session_invalidated:
        delete_angel_session(device_id)
        return False
    session = load_angel_session(device_id)
    if not session or not session.get("api_key") or not session.get("client_code"):
        return False
    try:
        restored = state.angel.restore_session(
            api_key=session["api_key"],
            client_code=session["client_code"],
            jwt=session.get("jwt"),
            refresh=session.get("refresh"),
            feed=session.get("feed"),
        )
        if restored:
            tokens = state.angel.session_tokens()
            if tokens.get("jwt"):
                save_angel_session(
                    device_id,
                    client_code=session["client_code"],
                    api_key=session["api_key"],
                    pin=session.get("pin"),
                    jwt=tokens["jwt"] or "",
                    refresh=tokens.get("refresh"),
                    feed=tokens.get("feed"),
                )
        return restored
    except Exception as exc:
        state.angel.authenticated = False
        state.angel.last_error = str(exc)
        return False



def load_device_ai(device_id: str) -> None:
    state.apply_ai(load_ai(device_id))


async def signal_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        state.last_cycle = datetime.now(timezone.utc)
        state.signals.cycle_once()
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=max(1, settings.engine_cycle_seconds)
            )
        except asyncio.TimeoutError:
            pass


async def ai_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        if settings.openrouter_api_key:
            for index, strategy in list(state.signals.latest.items()):
                if strategy.decision not in {TradeDecision.CALL_BUY, TradeDecision.PUT_BUY}:
                    # Never leave an earlier AI approval attached to a new WAIT/NO TRADE.
                    state.ai_latest.pop(index, None)
                    state.ai_keys.pop(index, None)
                    continue
                index_row = state.master.find_index(index)
                index_token = str(index_row.get("token", "")) if index_row else ""
                obi_all = state.obi.snapshot().get("signals", {})
                obi_summary = obi_all.get(index_token) if index_token else None
                obi_summary = obi_summary or {
                    "status": "WAIT",
                    "reason": "No underlying-index OBI depth signal available",
                }
                snapshot = state.signals.last_snapshot.get(index)
                selected_quote = None
                if snapshot is not None:
                    wanted_side = "CE" if strategy.decision == TradeDecision.CALL_BUY else "PE"
                    selected_quote = next(
                        (option for option in snapshot.options
                         if option.side == wanted_side and strategy.strike is not None
                         and abs(option.strike - strategy.strike) <= 0.001),
                        None,
                    )
                snapshot_key = (
                    f"{snapshot.timestamp.isoformat()}:{snapshot.source}:{snapshot.ltp}:"
                    if snapshot is not None else "NO_SNAPSHOT"
                )
                quote_key = (
                    f"{selected_quote.timestamp.isoformat()}:{selected_quote.ltp}:"
                    f"{selected_quote.bid}:{selected_quote.ask}:{selected_quote.oi}:"
                    f"{selected_quote.oi_change}"
                    if selected_quote is not None else "NO_OPTION_QUOTE"
                )
                fingerprint = hashlib.sha256((
                    f"{strategy.decision.value}:{strategy.strike}:{strategy.entry}:"
                    f"{strategy.stop_loss}:{strategy.target}:{strategy.confidence}:"
                    f"{strategy.guards}:{snapshot_key}:{quote_key}:"
                    f"OBI:{obi_summary.get('status')}:{obi_summary.get('obi')}:"
                    f"{obi_summary.get('micro_edge_bps')}:{obi_summary.get('momentum_bps')}"
                ).encode("utf-8")).hexdigest()
                if state.ai_keys.get(index) == fingerprint:
                    continue
                try:
                    search = SearchEvidenceService(
                        exa_key=state.credentials.exa_api_key,
                        tavily_key=state.credentials.tavily_api_key,
                        brave_key=state.credentials.brave_search_api_key,
                    )
                    query = search.query_for_index(index)
                    evidence = await search.search(query, max_results=4)
                    market_brief = None
                    if snapshot is not None:
                        adaptive = evaluate_adaptive_intelligence(snapshot)
                        market_brief = dict(adaptive["ai_brief"])
                        market_brief["order_book_imbalance"] = obi_summary
                        market_brief["agent_ensemble"] = build_agent_ensemble(
                            snapshot, strategy, market_brief=market_brief, evidence=evidence
                        )
                        market_brief["obi_safety_note"] = (
                            "OBI is an additional confirmation feature, not a standalone order instruction. "
                            "If OBI is WAIT, stale, or missing depth, explicitly mention that uncertainty."
                        )
                        guard = adaptive.get("decision_vote", {}).get("guard")
                        hard_guards = adaptive.get("hard_guards") or []
                        if hard_guards or guard:
                            state.ai_latest[index] = AIDecision(
                                index=index,
                                decision=TradeDecision.WAIT,
                                confidence=0.0,
                                action="SAFETY_BLOCK",
                                why=["Adaptive engine blocked AI confirmation because market data or risk guards failed."],
                                risk_flags=hard_guards + ([guard] if guard else []),
                                invalidation="Re-evaluate only after fresh, complete market data passes all deterministic gates.",
                                evidence_count=len(evidence),
                            )
                            state.ai_keys[index] = fingerprint
                            continue
                    state.ai_latest[index] = await state.signal_ai().decide(strategy, evidence, market_brief=market_brief)
                    state.ai_keys[index] = fingerprint
                except Exception as exc:
                    state.ai_latest[index] = AIDecision(
                        index=index,
                        decision=strategy.decision,
                        confidence=strategy.confidence,
                        action="AI_ERROR",
                        why=["AI enrichment failed: " + str(exc)],
                        risk_flags=["AI_ENRICHMENT_ERROR"],
                        invalidation="Wait for the next clean live cycle.",
                        evidence_count=0,
                    )
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=max(5, settings.ai_cycle_seconds)
            )
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_store()
    stop = asyncio.Event()
    signal_task = asyncio.create_task(signal_loop(stop))
    ai_task = asyncio.create_task(ai_loop(stop))
    try:
        yield
    finally:
        stop.set()
        signal_task.cancel()
        ai_task.cancel()


app = FastAPI(
    title="Fresh Algo Signal API",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "fresh-algo-signal",
        "cycle_at": state.last_cycle.isoformat(),
        "secure_store": "enabled",
    }


@app.get("/v1/system/diagnostics")
async def system_diagnostics(device_id: str = Depends(require_device_id)) -> dict:
    """Expose safe runtime diagnostics expected by the mobile app."""
    restore_device_angel(device_id)
    angel = state.angel.status()
    live = state.live_execution.status(state.angel)
    return {
        "status": "ok",
        "service": "fresh-algo-signal",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "last_signal_cycle_at": state.last_cycle.isoformat(),
        "angel": {
            "authenticated": bool(angel.get("authenticated")),
            "stream_started": bool(angel.get("stream_started")),
            "stream_open": bool(angel.get("stream_open")),
            "tick_count": int(angel.get("tick_count") or 0),
            "last_tick_at": angel.get("last_tick_at"),
            "last_tick_age_seconds": angel.get("last_tick_age_seconds"),
            "last_error": angel.get("stream_error") or angel.get("last_error"),
            "stored_session": bool(angel_session_status(device_id)),
        },
        "live_execution": live,
        "secure_store": "enabled",
    }


@app.get("/v1/metadata")
def metadata() -> dict:
    return {
        "indexes": list(AngelGateway.INDEXES.keys()),
        "tabs": [
            "Dashboard", "Market", "Option Chain", "OI Lab", "Indicators",
            "Signals", "Risk", "Commodities", "API", "AI Access",
        ],
        "order_placement_enabled": state.live_execution.enabled(),
        "trading_mode": "LIVE_GATED" if state.live_execution.enabled() else "SIGNAL_ONLY",
        "live_execution_allowed": state.live_execution.enabled(),
        "live_execution": state.live_execution.status(state.angel),
        "readiness_requirements": {
            "minimum_completed_trades": 100,
            "minimum_net_win_rate": 0.80,
            "positive_net_expectancy": True,
            "walk_forward_review_required": True,
            "human_approval_required": True,
        },
        "stale_data_seconds": settings.stale_data_seconds,
    }


@app.post("/v1/ai/chat")
async def ai_chat(
    payload: AIChatRequest,
    device_id: str = Depends(require_device_id),
) -> dict:
    """Answer a user question using configured server-side AI and available market context."""
    # Restore saved broker tokens if needed so market context can recover after resume.
    restore_device_angel(device_id)
    load_device_ai(device_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")
    if len(question) > 2000:
        raise HTTPException(status_code=413, detail="Question is too long (maximum 2000 characters).")
    if not state.credentials.openai_api_key:
        raise HTTPException(status_code=400, detail="Configure an OpenAI API key in AI Access first.")

    index = payload.index.upper().strip()
    if index not in AngelGateway.INDEXES:
        index = "NIFTY"
    snapshot = state.signals.last_snapshot.get(index)
    strategy = state.signals.latest.get(index)
    ai_decision = state.ai_latest.get(index)
    market_context = {
        "index": index,
        "market_data_available": snapshot is not None,
        "market_data_source": snapshot.source if snapshot is not None else "unavailable",
        "market_timestamp": snapshot.timestamp.isoformat() if snapshot is not None else None,
        "underlying_ltp": snapshot.ltp if snapshot is not None else None,
        "strategy": strategy.model_dump(mode="json") if strategy is not None else None,
        "ai_decision": ai_decision.model_dump(mode="json") if ai_decision is not None else None,
        "safety": "Treat missing or stale data as unknown. Do not invent prices or claim a quote is live unless its source and timestamp support that claim.",
    }
    messages = [{
        "role": "system",
        "content": (
            "You are Fresh Algo Signal's market research assistant. Answer the user's question clearly. "
            "Use only the supplied market context and clearly distinguish observed data from general explanation. "
            "If current data is absent, stale, or incomplete, say so and do not guess current prices, option-chain values, news, or P&L. "
            "Never guarantee returns, never represent an AI opinion as a sure trading signal, and never place or claim to place orders. "
            "Explain risk and uncertainty for trading-related questions. Market context JSON: "
            + __import__("json").dumps(market_context, ensure_ascii=False, default=str)
        ),
    }]
    for item in payload.history[-12:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": question})
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {state.credentials.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": state.credentials.openai_model or settings.openai_model,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {response.status_code}: {detail}")
        data = response.json()
        choices = data.get("choices") or []
        answer = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(answer, str) or not answer.strip():
            raise HTTPException(status_code=502, detail="AI provider returned an empty response.")
        return {
            "ok": True,
            "answer": answer.strip(),
            "model": data.get("model") or state.credentials.openai_model or settings.openai_model,
            "index": index,
            "market_context_available": snapshot is not None,
            "market_data_source": snapshot.source if snapshot is not None else "unavailable",
            "market_timestamp": snapshot.timestamp.isoformat() if snapshot is not None else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI chat request failed: {exc}") from exc


@app.post("/v1/providers/openai/test")
async def test_openai(device_id: str = Depends(require_device_id)) -> dict:
    load_device_ai(device_id)
    if not state.credentials.openai_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key is not configured")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {state.credentials.openai_api_key}"},
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI authentication failed ({response.status_code}): {detail}",
            )
        return {
            "ok": True,
            "provider": "openai",
            "model": state.credentials.openai_model or settings.openai_model,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI connection failed: {exc}") from exc


@app.post("/v1/settings/credentials")
def update_credentials(
    payload: AiCredentialsPayload,
    device_id: str = Depends(require_device_id),
) -> dict:
    load_device_ai(device_id)
    current = state.credentials.model_dump()
    incoming = payload.model_dump(exclude_none=True)
    # Empty fields mean "keep the encrypted value already saved for this device".
    # Do not blank the in-memory runtime configuration while the database keeps
    # the prior key, otherwise the AI loop silently stops using saved providers.
    incoming = {
        key: value
        for key, value in incoming.items()
        if not isinstance(value, str) or value.strip()
    }
    current.update(incoming)
    state.credentials = CredentialPayload(**current)
    save_ai(
        device_id,
        openai_key=payload.openai_api_key,
        model=state.credentials.openai_model or settings.openai_model,
        exa_key=payload.exa_api_key,
        tavily_key=payload.tavily_api_key,
        brave_key=payload.brave_search_api_key,
    )
    state.ai_latest.clear()
    state.ai_keys.clear()
    return {
        "ok": True,
        "stored": "server-side-encrypted",
        "openai_configured": bool(state.credentials.openai_api_key),
        "search_providers": {
            "exa": bool(state.credentials.exa_api_key),
            "tavily": bool(state.credentials.tavily_api_key),
            "brave": bool(state.credentials.brave_search_api_key),
        },
    }


@app.post("/v1/providers/search/test")
async def test_search_providers(device_id: str = Depends(require_device_id)) -> dict:
    load_device_ai(device_id)
    service = SearchEvidenceService(
        exa_key=state.credentials.exa_api_key,
        tavily_key=state.credentials.tavily_api_key,
        brave_key=state.credentials.brave_search_api_key,
    )
    if not service.configured_providers:
        raise HTTPException(status_code=400, detail="Configure at least one search provider")
    query = service.query_for_index("NIFTY 50")
    results = await service.search(query, max_results=2)
    providers_with_results = sorted({item.provider for item in results})
    return {
        "ok": bool(results),
        "configured": service.configured_providers,
        "responding": providers_with_results,
        "evidence_count": len(results),
        "message": "Search providers returned evidence." if results else
                   "No results returned. Check provider keys, quotas, network and provider status.",
    }


@app.post("/v1/angel/connect")
async def connect_angel(
    payload: AngelConnectPayload,
    device_id: str = Depends(require_device_id),
) -> dict:
    # Remembered credentials are only read server-side; PIN and tokens are never
    # returned to the mobile app. TOTP is intentionally never persisted.
    saved = load_angel_session(device_id) or {}
    api_key = (payload.angel_api_key or "").strip() or str(saved.get("api_key") or "")
    client_code = (payload.angel_client_code or "").strip() or str(saved.get("client_code") or "")
    pin = (payload.angel_pin or "").strip() or str(saved.get("pin") or "")

    # A healthy in-memory session needs no second login or TOTP.
    if state.angel.authenticated:
        if payload.remember_credentials and api_key and client_code and pin:
            tokens = state.angel.session_tokens()
            if tokens.get("jwt") and tokens.get("feed"):
                save_angel_session(
                    device_id,
                    client_code=client_code,
                    api_key=api_key,
                    pin=pin,
                    jwt=tokens["jwt"] or "",
                    refresh=tokens.get("refresh"),
                    feed=tokens.get("feed"),
                )
        elif not payload.remember_credentials:
            delete_angel_session(device_id)
        return {
            "authenticated": True,
            "client_code": state.angel.client_code or client_code,
            "has_jwt_token": bool(state.angel.auth_token),
            "has_feed_token": bool(state.angel.feed_token),
            "session_restored": True,
            "totp_required": False,
            "remembered_credentials": "server-side-encrypted" if payload.remember_credentials else False,
            "message": "Existing Angel session is already authenticated.",
        }

    # Try restoring/refreshing a saved token before asking for a fresh TOTP.
    if saved and not payload.angel_totp:
        if restore_device_angel(device_id):
            if not payload.remember_credentials:
                delete_angel_session(device_id)
            return {
                "authenticated": True,
                "client_code": state.angel.client_code or client_code,
                "has_jwt_token": bool(state.angel.auth_token),
                "has_feed_token": bool(state.angel.feed_token),
                "session_restored": True,
                "totp_required": False,
                "message": "Saved Angel session restored; no new login required.",
            }
        raise HTTPException(
            status_code=401,
            detail="Saved Angel session expired or was rejected. Enter the current 6-digit TOTP to sign in again.",
        )

    if not api_key or not client_code or not pin:
        raise HTTPException(
            status_code=400,
            detail="Enter API Key, Client ID and MPIN once, then enable Remember credentials.",
        )
    if not payload.angel_totp:
        raise HTTPException(
            status_code=400,
            detail="Current 6-digit TOTP is required only for a fresh Angel One login.",
        )

    try:
        result = state.angel.connect(api_key, client_code, pin, payload.angel_totp)
        if result.get("authenticated") is not True:
            raise RuntimeError(str(result.get("login_message") or "Angel One did not authenticate the session"))
        tokens = state.angel.session_tokens()
        missing_tokens = [
            name for name, value in (("jwtToken", tokens.get("jwt")), ("feedToken", tokens.get("feed")))
            if not value
        ]
        if missing_tokens:
            state.angel.authenticated = False
            raise RuntimeError("Angel login response is incomplete; missing " + ", ".join(missing_tokens))
        if payload.remember_credentials:
            save_angel_session(
                device_id,
                client_code=client_code,
                api_key=api_key,
                pin=pin,
                jwt=tokens["jwt"] or "",
                refresh=tokens.get("refresh"),
                feed=tokens.get("feed"),
            )
        else:
            delete_angel_session(device_id)
        state.credentials = CredentialPayload(
            **{
                **state.credentials.model_dump(),
                "angel_api_key": None,
                "angel_client_code": client_code,
                "angel_pin": None,
                "angel_totp": None,
            }
        )

        async def start_feed_after_login() -> None:
            try:
                await ensure_live_feed()
                await poll_rest_index_quotes(list(AngelGateway.INDEXES.keys()))
            except Exception as feed_exc:
                state.angel.last_error = "Feed startup failed: " + str(feed_exc)

        asyncio.create_task(start_feed_after_login())
        return {
            **result,
            "feed_starting": True,
            "session_restored": False,
            "totp_required": False,
            "remembered_credentials": "server-side-encrypted" if payload.remember_credentials else False,
            "password_stored": bool(payload.remember_credentials),
            "totp_stored": False,
            "jwt_stored": "server-side-encrypted",
        }
    except HTTPException:
        raise
    except Exception as exc:
        state.angel.authenticated = False
        state.angel.last_error = str(exc)
        raise HTTPException(
            status_code=502,
            detail=f"Angel One connection failed: {exc}",
        ) from exc


@app.get("/v1/angel/status")
async def angel_status(device_id: str = Depends(require_device_id)) -> dict:
    restore_device_angel(device_id)
    # Make diagnostics self-healing: opening/polling the API tab should ensure
    # that an authenticated session has a stream and a REST quote fallback.
    if state.angel.authenticated:
        try:
            indexes = list(AngelGateway.INDEXES.keys())
            await ensure_live_feed(indexes)
            await poll_rest_index_quotes(indexes)
        except Exception as exc:
            state.angel.last_error = "Feed health check failed: " + str(exc)
    live = state.angel.status()
    stored = angel_session_status(device_id)
    return {
        **live,
        "last_error": live.get("stream_error") or live.get("last_error"),
        "feed_error": live.get("stream_error") or live.get("last_error"),
        "stored_session": bool(stored),
        "stored_session_updated_at": stored["updated_at"] if stored else None,
        "stored_jwt": bool(stored and stored["has_jwt"]),
        "stored_feed_token": bool(stored and stored["has_feed_token"]),
        "stored_api_key": bool(stored and stored.get("has_saved_api_key")),
        "stored_pin": bool(stored and stored.get("has_saved_pin")),
    }


@app.post("/v1/instruments/sync")
async def sync_instruments() -> dict:
    try:
        return await state.master.sync()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Instrument master sync failed"
        ) from exc


@app.get("/v1/instruments/options/{index}")
def option_instruments(index: str) -> dict:
    if not state.master.rows and not state.master.load_cache():
        raise HTTPException(status_code=409, detail="Run instrument sync first")
    rows = state.master.option_rows(index.upper())
    return {
        "index": index.upper(),
        "count": len(rows),
        "items": rows[:300],
    }


@app.post("/v1/stream/start")
async def start_stream(
    payload: StreamRequest,
    device_id: str = Depends(require_device_id),
) -> dict:
    # Restore this device's encrypted Angel session before trying to start its feed.
    restore_device_angel(device_id)
    if not state.angel.authenticated:
        raise HTTPException(
            status_code=503,
            detail="Angel One session is not connected. Log in to Angel One, then start the live stream.",
        )
    if not state.master.rows:
        if not state.master.load_cache():
            await state.master.sync()

    indexes_to_watch = [
        x.upper() for x in (payload.indexes or list(AngelGateway.INDEXES.keys()))
    ]
    token_list = build_subscription_groups(indexes_to_watch)
    total = sum(len(item["tokens"]) for item in token_list)
    if not token_list:
        raise HTTPException(
            status_code=409,
            detail="No instrument tokens found for selected indexes",
        )
    if total > 950:
        raise HTTPException(
            status_code=422,
            detail=f"Subscription set too large: {total}. Narrow the expiry/strike universe.",
        )

    try:
        await warmup_historical_timeframes(indexes_to_watch)
        state.signals.indexes = indexes_to_watch
        state.angel.start_stream(token_list, on_tick=state.obi.on_tick)
        return {
            "started": True,
            "indexes": indexes_to_watch,
            "subscriptions": total,
            "groups": token_list,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Live stream start failed: {exc}",
        ) from exc


@app.get("/v1/market/ticks")
def market_ticks() -> dict:
    ticks = state.angel.market_store.snapshot()
    return {
        **state.angel.market_store.diagnostics(),
        "stream": state.angel.status(),
        "count": len(ticks),
        "ticks": ticks,
    }


@app.get("/v1/signals")
@app.get("/api/v1/signals", include_in_schema=False)
@app.get("/api/signals", include_in_schema=False)
async def live_signals(
    ema_fast: int = 8,
    ema_slow: int = 13,
    device_id: str = Depends(require_device_id),
) -> dict:
    load_device_ai(device_id)
    restore_device_angel(device_id)
    if not state.signals.last_snapshot:
        state.signals.restore_snapshots(load_market_snapshots(device_id))
    if state.angel.authenticated:
        try:
            indexes_to_watch = list(AngelGateway.INDEXES.keys())
            await ensure_live_feed(indexes_to_watch)
            await warmup_historical_timeframes(indexes_to_watch)
            await poll_rest_index_quotes(indexes_to_watch)
            # The WebSocket callback fills MarketStore. Build normalized snapshots
            # from that shared store on every API refresh so Market, OI and Signals
            # all consume the same broker ticks instead of an unrefreshed empty cache.
            for index in indexes_to_watch:
                snapshot = state.signals.build_snapshot(index)
                if snapshot is None:
                    continue
                state.signals.last_snapshot[index] = snapshot
                result = analyze(snapshot, settings.stale_data_seconds, ema_fast, ema_slow)
                state.signals.latest[index] = state.signals._apply_trade_desk(index, snapshot, result)
        except Exception as exc:
            state.angel.last_error = "Market data refresh failed: " + str(exc)
    if ema_fast >= ema_slow:
        ema_fast, ema_slow = 8, 13
    if ema_fast != 8 or ema_slow != 13:
        for key, snapshot in list(state.signals.last_snapshot.items()):
            result = analyze(snapshot, settings.stale_data_seconds, ema_fast, ema_slow)
            state.signals.latest[key] = state.signals._apply_trade_desk(key, snapshot, result)
    if state.signals.last_snapshot:
        save_market_snapshots(
            device_id,
            {
                index: snapshot.model_dump(mode="json")
                for index, snapshot in state.signals.last_snapshot.items()
            },
        )

    plans = build_qualified_trade_plans(list(state.signals.latest.values()), limit=5)
    market = {}
    for index, snapshot in state.signals.last_snapshot.items():
        options = sorted(
            snapshot.options,
            key=lambda o: (abs(o.strike - snapshot.ltp), o.side),
        )[:60]
        age_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - snapshot.timestamp).total_seconds(),
        )
        stream_status = state.angel.status()
        websocket_fresh = (
            snapshot.source == "angel-one-websocket"
            and stream_status.get("last_tick_age_seconds") is not None
            and stream_status["last_tick_age_seconds"] <= settings.stale_data_seconds
        )
        data_fresh = age_seconds <= settings.stale_data_seconds and state.angel.authenticated
        chain = []
        for option in options:
            option_age = max(
                0.0,
                (datetime.now(timezone.utc) - option.timestamp).total_seconds(),
            )
            item = option.model_dump(mode="json")
            item["age_seconds"] = round(option_age, 1)
            item["live"] = option_age <= settings.stale_data_seconds and state.angel.authenticated
            option_tick = state.angel.market_store.get(option.token or "")
            item["source"] = (option_tick or {}).get("source", "unknown")
            chain.append(item)
        market[index] = {
            "ltp": snapshot.ltp,
            "timestamp": snapshot.timestamp.isoformat(),
            "source": snapshot.source,
            "age_seconds": round(age_seconds, 1),
            "live": data_fresh,
            "feed_mode": (
                "LIVE WEBSOCKET" if websocket_fresh
                else "REST FALLBACK" if data_fresh and snapshot.source == "angel-one-rest-fallback"
                else "STALE / CACHED"
            ),
            "last_fetch_label": (
                "LIVE WS" if websocket_fresh
                else "REST FALLBACK" if data_fresh and snapshot.source == "angel-one-rest-fallback"
                else "LAST FETCH"
            ),
            "timeframes": snapshot.timeframes,
            "option_chain": chain,
        }
    commodities = []
    now_epoch = time.time()
    for row in state.master.commodity_rows():
        token = str(row.get("token", ""))
        tick = state.angel.market_store.get(token) if token else None
        received_at = float((tick or {}).get("received_at", 0) or 0)
        age = max(0.0, now_epoch - received_at) if received_at else None
        raw_ltp = (tick or {}).get("last_traded_price") or (tick or {}).get("ltp")
        try:
            ltp = float(raw_ltp) if raw_ltp is not None else None
            if ltp is not None and ltp > 100000:
                ltp /= 100.0
        except (TypeError, ValueError):
            ltp = None
        commodities.append({
            "name": str(row.get("name") or row.get("symbol") or "Commodity"),
            "symbol": str(row.get("symbol") or ""),
            "token": token,
            "exchange": "MCX",
            "expiry": row.get("expiry"),
            "lotsize": row.get("lotsize") or row.get("lot_size"),
            "ltp": ltp,
            "source": (tick or {}).get("source", "NO DATA"),
            "timestamp": datetime.fromtimestamp(received_at, timezone.utc).isoformat() if received_at else None,
            "age_seconds": round(age, 1) if age is not None else None,
            "live": bool(state.angel.authenticated and age is not None and age <= settings.stale_data_seconds and ltp is not None),
        })

    return {
        "generated_at": state.last_cycle.isoformat(),
        "commodities": commodities,
        "live": any(item.get("live") is True for item in market.values()),
        "feed": state.angel.status(),
        "store": state.angel.market_store.diagnostics(),
        "obi": state.obi.snapshot(),
        "last_fetch": max((s.timestamp.isoformat() for s in state.signals.last_snapshot.values()), default=None),
        "qualified_trade_count": len(plans),
        "trade_plans": plans,
        "market": market,
        "signals": {
            key: {
                **value.model_dump(mode="json"),
                "research_pack": evaluate_research_pack(
                    state.signals.last_snapshot.get(key),
                    value.decision,
                    indicators=value.indicators,
                ),
                "live_validation": validate_live_candidate(
                    value,
                    state.signals.last_snapshot.get(key),
                    state.ai_latest.get(key),
                    stale_after_seconds=settings.stale_data_seconds,
                ),
            }
            for key, value in state.signals.latest.items()
        },
        "ai": {
            key: value.model_dump(mode="json")
            for key, value in state.ai_latest.items()
        },
    }


@app.get("/v1/obi/signals")
def obi_signals() -> dict:
    """Latest signal-only order-book imbalance diagnostics."""
    return state.obi.snapshot()


@app.get("/v1/signals/{index}")
def live_signal(index: str, device_id: str = Depends(require_device_id)) -> dict:
    load_device_ai(device_id)
    key = index.upper()
    if key not in state.signals.latest:
        raise HTTPException(status_code=404, detail="No signal available for index")
    strategy = state.signals.latest[key]
    snapshot = state.signals.last_snapshot.get(key)
    ai = state.ai_latest.get(key)
    return {
        "strategy": strategy.model_dump(mode="json"),
        "ai": ai.model_dump(mode="json") if ai is not None else None,
        "live_validation": validate_live_candidate(
            strategy,
            snapshot,
            ai,
            stale_after_seconds=settings.stale_data_seconds,
        ),
    }


@app.get("/v1/live/status")
def live_execution_status(device_id: str = Depends(require_device_id)) -> dict:
    return state.live_execution.status(state.angel)


@app.post("/v1/live/execute-signal")
def execute_live_signal(
    payload: LiveOrderRequest,
    device_id: str = Depends(require_device_id),
) -> dict:
    """Submit a real Angel One limit order from the current qualified CALL/PUT signal."""
    index = payload.index.upper().strip()
    if index not in AngelGateway.INDEXES:
        raise HTTPException(status_code=422, detail="Unsupported index. Choose a configured F&O index.")
    signal = state.signals.latest.get(index)
    snapshot = state.signals.last_snapshot.get(index)
    if snapshot is None:
        raise HTTPException(status_code=409, detail="No current market snapshot; live order blocked.")
    age = max(0.0, (datetime.now(timezone.utc) - snapshot.timestamp).total_seconds())
    if age > settings.stale_data_seconds:
        raise HTTPException(status_code=409, detail="Signal snapshot is stale; wait for fresh Angel One market data.")
    validation = validate_live_candidate(
        signal,
        snapshot,
        state.ai_latest.get(index),
        stale_after_seconds=settings.stale_data_seconds,
    )
    if validation["verdict"] != "PASS":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Live AI validation did not pass; no real order was sent.",
                "validation": validation,
            },
        )
    try:
        return state.live_execution.execute_qualified_signal(
            gateway=state.angel,
            master=state.master,
            store=state.angel.market_store,
            index=index,
            lots=payload.lots,
            confirmation=payload.confirmation,
            request_id=payload.request_id,
            stale_after_seconds=settings.stale_data_seconds,
            signal=signal,
        )
    except LiveExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/live/orders")
def live_order_book(device_id: str = Depends(require_device_id)) -> dict:
    if not state.angel.authenticated or state.angel.client is None:
        raise HTTPException(status_code=401, detail="Angel One is not authenticated.")
    try:
        response = state.angel.client.orderBook()
        if not isinstance(response, dict) or response.get("status") is False:
            raise RuntimeError(str((response or {}).get("message", "Angel One order book request failed")))
        return {
            "broker": "Angel One SmartAPI",
            "status": "OK",
            "orders": response.get("data") or [],
            "live_execution": state.live_execution.status(state.angel),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch Angel One order book: {exc}") from exc


@app.get("/v1/portfolio")
def portfolio() -> dict:
    try:
        return {
            "holdings": state.angel.holdings(),
            "positions": state.angel.positions(),
        }
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/analysis")
async def run_analysis(request: AnalysisRequest) -> dict:
    strategy: StrategyResult = analyze(
        request.snapshot, settings.stale_data_seconds
    )
    evidence = []  # Search-provider integrations removed; use structured snapshot + OpenAI only.
    ai: AIDecision = await state.ai().decide(strategy, evidence)
    return {"strategy": strategy, "evidence": evidence, "ai": ai}


@app.post("/v1/paper/trades/open")
def paper_open(payload: PaperOpenPayload, device_id: str = Depends(require_device_id)) -> dict:
    try:
        return state.paper_monitor(device_id).open_trade(
            payload.trade_id, payload.strategy_id, payload.index.upper(),
            payload.side.upper(), payload.regime.upper(),
            slippage_r=payload.slippage_r,
            transaction_cost_r=payload.transaction_cost_r,
            notes=payload.notes,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/paper/trades/{trade_id}/close")
def paper_close(trade_id: str, payload: PaperClosePayload,
                device_id: str = Depends(require_device_id)) -> dict:
    try:
        return state.paper_monitor(device_id).close_trade(
            trade_id, payload.gross_r, notes=payload.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/paper/report")
def paper_report(device_id: str = Depends(require_device_id)) -> dict:
    return state.paper_monitor(device_id).report()


@app.get("/v1/paper/trades")
def paper_trades(device_id: str = Depends(require_device_id)) -> dict:
    monitor = state.paper_monitor(device_id)
    return {"mode": "PAPER_ONLY", "trades": monitor.trades(), "risk": monitor.kill_switch()}


@app.post("/v1/backtest/historical")
async def historical_backtest(payload: HistoricalBacktestRequest, device_id: str = Depends(require_device_id)) -> dict:
    """Replay real Angel One historical index candles through a deterministic EMA/ATR baseline."""
    if not state.angel.authenticated:
        raise HTTPException(status_code=401, detail="Connect Angel One before running historical backtests.")
    index = payload.index.upper().strip()
    if index not in AngelGateway.INDEXES:
        raise HTTPException(status_code=422, detail="Unsupported index. Choose a configured F&O index.")
    if payload.interval not in {"ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "ONE_HOUR"}:
        raise HTTPException(status_code=422, detail="Unsupported interval.")
    try:
        from_day = datetime.strptime(payload.from_date, "%Y-%m-%d").date()
        to_day = datetime.strptime(payload.to_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD.") from exc
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if from_day > to_day or to_day > today_ist or (to_day - from_day).days > 30:
        raise HTTPException(status_code=422, detail="Choose a valid historical range of at most 30 days, ending no later than today.")
    if not state.master.rows:
        if not state.master.load_cache():
            await state.master.sync()
    instrument = state.master.find_index(index)
    if not instrument or not instrument.get("token"):
        raise HTTPException(status_code=409, detail="Index token is missing from the Angel One instrument master.")
    exchange = str(instrument.get("exch_seg") or AngelGateway.INDEXES[index]["exchange"]).upper()
    fromdate = f"{payload.from_date} 09:15"
    todate = f"{payload.to_date} 15:30"
    try:
        rows = await asyncio.to_thread(
            state.angel.historical_candles,
            exchange=exchange,
            token=str(instrument["token"]),
            interval=payload.interval,
            fromdate=fromdate,
            todate=todate,
        )
        report = run_ema_atr_backtest(
            rows,
            fast_period=payload.fast_ema,
            slow_period=payload.slow_ema,
            atr_period=payload.atr_period,
            stop_atr=payload.stop_atr,
            target_r=payload.target_r,
            max_hold_bars=payload.max_hold_bars,
            slippage_r=payload.slippage_r,
            transaction_cost_r=payload.transaction_cost_r,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Angel One historical candles failed: {exc}") from exc
    return {
        "ok": True,
        "index": index,
        "exchange": exchange,
        "interval": payload.interval,
        "requested_from": fromdate,
        "requested_to": todate,
        "report": report,
        "live_execution_allowed": False,
    }


@app.post("/v1/backtest/report")
def backtest_report(payload: BacktestRequest, device_id: str = Depends(require_device_id)) -> dict:
    if payload.folds < 2 or payload.folds > 20:
        raise HTTPException(status_code=422, detail="folds must be between 2 and 20")
    if payload.slippage_r < 0 or payload.transaction_cost_r < 0:
        raise HTTPException(status_code=422, detail="cost assumptions cannot be negative")
    report = walk_forward_report(payload.trades, folds=payload.folds, slippage_r=payload.slippage_r, transaction_cost_r=payload.transaction_cost_r)
    return {"ok": True, "mode": "ANALYSIS_ONLY", "live_execution_allowed": False, "report": report}


@app.post("/v1/backtest/readiness")
def backtest_readiness(payload: BacktestRequest, device_id: str = Depends(require_device_id)) -> dict:
    return {"ok": True, **evaluate_readiness(payload.trades, slippage_r=payload.slippage_r, transaction_cost_r=payload.transaction_cost_r)}


@app.get("/v1/paper/monitor")
def paper_monitor_summary(device_id: str = Depends(require_device_id)) -> dict:
    return {"ok": True, **state.paper_monitor(device_id).report(), "live_execution_allowed": False}