from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TradeDecision(str, Enum):
    CALL_BUY = "CALL BUY"
    PUT_BUY = "PUT BUY"
    WAIT = "WAIT"
    NO_TRADE = "NO TRADE"


class OISignal(str, Enum):
    LONG_BUILDUP = "LONG BUILDUP"
    SHORT_BUILDUP = "SHORT BUILDUP"
    SHORT_COVERING = "SHORT COVERING"
    LONG_UNWINDING = "LONG UNWINDING"
    NEUTRAL = "NEUTRAL"


class OptionPoint(BaseModel):
    symbol: str
    strike: float
    side: str
    ltp: float
    bid: float | None = None
    ask: float | None = None
    volume: float = 0
    token: str | None = None
    expiry: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None
    dte: float | None = None
    oi: float = 0
    oi_change: float = 0
    premium_change: float = 0
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketSnapshot(BaseModel):
    index: str
    exchange: str
    ltp: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    volume: float = 0
    candles: list[float] = Field(default_factory=list)
    vwap: float | None = None
    options: list[OptionPoint] = Field(default_factory=list)
    timeframes: dict[str, list[dict[str, float | str]]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "angel-one"


class StrategyResult(BaseModel):
    index: str
    decision: TradeDecision
    confidence: float = Field(ge=0, le=100)
    regime: str
    strike: float | None = None
    option_side: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    reason: list[str] = Field(default_factory=list)
    guards: list[str] = Field(default_factory=list)
    oi_summary: dict[str, float | str] = Field(default_factory=dict)
    indicators: dict[str, float | str] = Field(default_factory=dict)
    timeframe_analysis: dict[str, Any] = Field(default_factory=dict)
    trade_plan: dict[str, Any] | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchEvidence(BaseModel):
    provider: str
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None


class AIDecision(BaseModel):
    index: str
    decision: TradeDecision
    confidence: float = Field(ge=0, le=100)
    action: str
    why: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    invalidation: str
    evidence_count: int = 0
    agent_analysis: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
