from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Any

from .models import MarketSnapshot, OptionPoint, StrategyResult, TradeDecision
from .strategies import analyze

from backend.pipeline.ai_trading_engine import (
    build_trade_plan,
    choose_strike,
    evaluate_multi_timeframe,
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ltp(tick: dict[str, Any] | None) -> float:
    if not tick:
        return 0.0
    value = tick.get("last_traded_price", tick.get("ltp", 0))
    number = _number(value)
    # SmartAPI websocket prices are commonly delivered in paise.
    return number / 100.0 if number > 100000 else number


def _timestamp(tick: dict[str, Any] | None) -> datetime:
    """Use exchange/receive timestamps; never refresh missing or malformed ticks to now."""
    if not tick:
        return datetime.fromtimestamp(0, timezone.utc)
    for key in ("exchange_timestamp", "timestamp", "received_at"):
        raw = tick.get(key)
        if raw is None or raw == "":
            continue
        try:
            seconds = float(raw)
            if seconds > 10_000_000_000:
                seconds /= 1000.0
            if seconds > 0:
                return datetime.fromtimestamp(seconds, timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    # An unknown timestamp must fail freshness checks rather than look live.
    return datetime.fromtimestamp(0, timezone.utc)

def _strike(row: dict[str, Any]) -> float:
    raw = _number(row.get("strike"), 0.0)
    # Instrument master stores derivative strikes with exchange scaling on some rows.
    return raw / 100.0 if raw >= 100000 else raw


class SignalRuntime:
    """Turns broker ticks + instrument metadata into continuously refreshed strategy results."""

    def __init__(
        self,
        master: Any,
        store: Any,
        indexes: list[str] | None = None,
        stale_after_seconds: int = 15,
    ) -> None:
        self.master = master
        self.store = store
        self.indexes = indexes or ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
        self.stale_after_seconds = stale_after_seconds
        self.history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
        self.previous_options: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
        self.latest: dict[str, StrategyResult] = {}
        self.last_snapshot: dict[str, MarketSnapshot] = {}
        self.bars: dict[str, dict[str, deque[dict[str, Any]]]] = defaultdict(
            lambda: {tf: deque(maxlen=1500) for tf in ("1m", "5m", "15m")}
        )

    @staticmethod
    def _dte(row: dict[str, Any]) -> float | None:
        raw = str(row.get("expiry", "")).strip()
        for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
            try:
                return max(0.0, (datetime.strptime(raw.title(), fmt).date() - date.today()).days)
            except ValueError:
                continue
        return None

    def _update_bars(self, index: str, tick: dict[str, Any]) -> None:
        ltp = _ltp(tick)
        if ltp <= 0:
            return
        ts = _timestamp(tick).timestamp()
        volume = _number(tick.get("volume_trade_for_the_day", tick.get("volume", 0)))
        for tf, seconds in (("1m", 60), ("5m", 300), ("15m", 900)):
            bucket = float(int(ts // seconds) * seconds)
            bars = self.bars[index][tf]
            if bars and float(bars[-1]["start_epoch"]) == bucket:
                bar = bars[-1]
                bar["high"] = max(float(bar["high"]), ltp)
                bar["low"] = min(float(bar["low"]), ltp)
                bar["close"] = ltp
                bar["volume"] = volume
                bar["count"] = int(bar["count"]) + 1
            else:
                bars.append({
                    "start_epoch": bucket,
                    "start": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
                    "open": ltp,
                    "high": ltp,
                    "low": ltp,
                    "close": ltp,
                    "volume": volume,
                    "count": 1,
                })

    def _resample_higher_timeframes(self, index: str) -> None:
        source = list(self.bars[index]["1m"])
        for tf, seconds in (("5m", 300), ("15m", 900)):
            out = self.bars[index][tf]
            out.clear()
            current: dict[str, Any] | None = None
            for bar in source:
                bucket = float(int(float(bar["start_epoch"]) // seconds) * seconds)
                if current is None or float(current["start_epoch"]) != bucket:
                    if current is not None:
                        out.append(current)
                    current = {
                        "start_epoch": bucket,
                        "start": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
                        "open": float(bar["open"]),
                        "high": float(bar["high"]),
                        "low": float(bar["low"]),
                        "close": float(bar["close"]),
                        "volume": float(bar.get("volume", 0)),
                        "count": int(bar.get("count", 1)),
                    }
                else:
                    current["high"] = max(float(current["high"]), float(bar["high"]))
                    current["low"] = min(float(current["low"]), float(bar["low"]))
                    current["close"] = float(bar["close"])
                    current["volume"] = float(bar.get("volume", 0))
                    current["count"] = int(current["count"]) + int(bar.get("count", 1))
            if current is not None:
                out.append(current)

    def seed_from_historical(self, index: str, timeframe: str, rows: list[list[Any]]) -> None:
        bars = self.bars[index].get(timeframe)
        if bars is None:
            return
        bars.clear()
        for row in rows:
            try:
                ts = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                values = [float(row[i]) for i in range(1, 6)]
            except (TypeError, ValueError, IndexError):
                continue
            epoch = ts.timestamp()
            bars.append({
                "start_epoch": epoch,
                "start": ts.astimezone(timezone.utc).isoformat(),
                "open": values[0],
                "high": values[1],
                "low": values[2],
                "close": values[3],
                "volume": values[4],
                "count": 1,
            })
        if timeframe == "1m":
            self._resample_higher_timeframes(index)

    def needs_historical(self, index: str) -> bool:
        return not all(len(self.bars[index].get(tf, ())) >= 25 for tf in ("1m", "5m", "15m"))

    def timeframe_closes(self, index: str) -> dict[str, list[float]]:
        return {
            tf: [float(bar["close"]) for bar in self.bars[index][tf]]
            for tf in ("1m", "5m", "15m")
        }

    def _option_point(self, index: str, row: dict[str, Any], tick: dict[str, Any]) -> OptionPoint | None:
        symbol = str(row.get("symbol", ""))
        side = "CE" if symbol.upper().endswith("CE") else "PE" if symbol.upper().endswith("PE") else ""
        if not side:
            return None

        ltp = _ltp(tick)
        if ltp <= 0:
            return None

        token = str(row.get("token", ""))
        previous_ltp, previous_oi = self.previous_options[index].get(token, (ltp, _number(tick.get("open_interest"), 0)))
        oi = _number(tick.get("open_interest"), 0)
        premium_change = ((ltp - previous_ltp) / previous_ltp) if previous_ltp else 0.0
        oi_change = oi - previous_oi
        self.previous_options[index][token] = (ltp, oi)

        return OptionPoint(
            symbol=symbol or index,
            strike=_strike(row),
            side=side,
            ltp=ltp,
            volume=_number(
                tick.get("volume_trade_for_the_day", tick.get("volume_traded_for_the_day", tick.get("volume", 0)))
            ),
            oi=oi,
            oi_change=oi_change,
            premium_change=premium_change,
            iv=_number(tick.get("implied_volatility"), 0) or None,
            delta=_number(tick.get("delta"), 0) or None,
            gamma=_number(tick.get("gamma"), 0) or None,
            theta=_number(tick.get("theta"), 0) or None,
            vega=_number(tick.get("vega"), 0) or None,
            bid=_number(tick.get("best_bid"), 0) or None,
            ask=_number(tick.get("best_ask"), 0) or None,
            token=token or None,
            expiry=str(row.get("expiry", "")) or None,
            lot_size=int(float(row.get("lotsize") or 0)) or None,
            tick_size=_number(row.get("tick_size"), 0) or None,
            dte=self._dte(row),
            timestamp=_timestamp(tick),
        )

    def build_snapshot(self, index: str) -> MarketSnapshot | None:
        row = self.master.find_index(index)
        if not row:
            return None

        token = str(row.get("token", ""))
        tick = self.store.get(token)
        ltp = _ltp(tick)
        if ltp <= 0:
            return None

        self._update_bars(index, tick)
        # Rebuild higher timeframes from the same 1m history after every tick,
        # including after historical warm-up, so indicators don't read stale 5m/15m bars.
        self._resample_higher_timeframes(index)
        closes_1m = [float(bar["close"]) for bar in self.bars[index]["1m"]]
        self.history[index].clear()
        self.history[index].extend(closes_1m[-200:])

        options: list[OptionPoint] = []
        for option_row in self.master.option_rows(index):
            option_tick = self.store.get(str(option_row.get("token", "")))
            if option_tick:
                point = self._option_point(index, option_row, option_tick)
                if point:
                    options.append(point)

        return MarketSnapshot(
            index=index,
            exchange=str(row.get("exch_seg", "NSE")),
            ltp=ltp,
            candles=list(self.history[index]),
            options=options,
            timeframes={
                tf: [dict(bar) for bar in self.bars[index][tf]]
                for tf in ("1m", "5m", "15m")
            },
            timestamp=_timestamp(tick),
            source=str(tick.get("source") or "angel-one-websocket"),
        )

    def restore_snapshots(self, snapshots: dict[str, dict]) -> None:
        """Restore the most recent server-persisted snapshots after a process restart."""
        for index, raw in snapshots.items():
            try:
                snapshot = MarketSnapshot.model_validate(raw)
            except Exception:
                continue
            key = index.upper()
            self.last_snapshot[key] = snapshot
            result = analyze(snapshot, self.stale_after_seconds)
            if "LIVE_FEED_UNAVAILABLE" not in result.guards:
                result.guards.append("LIVE_FEED_UNAVAILABLE")
            result.reason = [
                "LIVE FEED UNAVAILABLE — showing the last fetched market snapshot.",
                *result.reason,
            ]
            if snapshot.timeframes:
                for tf in ("1m", "5m", "15m"):
                    self.seed_from_historical(key, tf, snapshot.timeframes.get(tf, []))
            self.latest[key] = self._apply_trade_desk(key, snapshot, result)

    def _apply_trade_desk(self, index: str, snapshot: MarketSnapshot, result: StrategyResult) -> StrategyResult:
        if result.decision not in {TradeDecision.CALL_BUY, TradeDecision.PUT_BUY}:
            return result
        side = "CE" if result.decision == TradeDecision.CALL_BUY else "PE"
        mtf = evaluate_multi_timeframe(self.timeframe_closes(index), side)
        result.timeframe_analysis = mtf
        if any(key.startswith("INSUFFICIENT_") for key in mtf.get("blocks", [])):
            result.guards.append("MTF_WARMUP_INCOMPLETE")
            result.reason.insert(0, "AI Trading Desk waiting for complete 1m/5m/15m historical context; no trade plan is qualified yet.")
            return result
        if not mtf.get("eligible"):
            result.guards.extend([g for g in mtf.get("blocks", []) if g not in result.guards])
            result.reason.insert(0, "AI Trading Desk vetoed entry: multi-timeframe alignment/trigger gate failed.")
            result.decision = TradeDecision.WAIT
            result.strike = None
            result.option_side = None
            result.entry = None
            result.stop_loss = None
            result.target = None
            result.trade_plan = None
            return result
        options = [o.model_dump(mode="json") for o in snapshot.options if o.side == side]
        if not options:
            result.decision = TradeDecision.WAIT
            result.guards.append("OPTION_CANDIDATE_MISSING")
            result.reason.insert(0, "AI Trading Desk vetoed entry: no option candidate.")
            return result
        try:
            chosen = choose_strike(options, side, snapshot.ltp)
            plan = build_trade_plan(
                index=index,
                side=side,
                strike=float(chosen["strike"]),
                option=chosen,
                timeframe=mtf,
                minutes_to_session_close=120,
            )
        except Exception as exc:
            result.decision = TradeDecision.WAIT
            result.guards.append("TRADE_PLAN_BUILD_ERROR")
            result.reason.insert(0, "AI Trading Desk trade-plan build failed safely: " + str(exc))
            return result
        result.trade_plan = plan if plan.get("eligible") else None
        if not plan.get("eligible"):
            result.decision = TradeDecision.WAIT
            result.guards.append(str(plan.get("reason", "TRADE_PLAN_REJECTED")))
            result.reason.insert(0, "AI Trading Desk vetoed entry: option execution/risk plan rejected.")
            return result
        result.strike = float(plan["strike"])
        result.option_side = side
        result.entry = float(plan["entry"])
        result.stop_loss = float(plan["stop_loss"])
        result.target = float(plan["target1"])
        result.confidence = min(float(result.confidence), float(plan["confidence"]))
        return result

    def cycle_once(self) -> dict[str, StrategyResult]:
        for index in self.indexes:
            snapshot = self.build_snapshot(index)
            if snapshot is None:
                cached = self.last_snapshot.get(index)
                if cached is not None:
                    result = analyze(cached, self.stale_after_seconds)
                    result.reason = [
                        "LIVE FEED UNAVAILABLE — showing last fetched market snapshot.",
                        *result.reason,
                    ]
                    if "LIVE_FEED_UNAVAILABLE" not in result.guards:
                        result.guards.append("LIVE_FEED_UNAVAILABLE")
                    self.latest[index] = result
                else:
                    self.latest[index] = StrategyResult(
                        index=index,
                        decision=TradeDecision.NO_TRADE,
                        confidence=0,
                        regime="NO_DATA",
                        reason=["No live or previously fetched market snapshot available."],
                        guards=["INDEX_TICK_MISSING", "NO_LAST_FETCH"],
                    )
                continue
            result = analyze(snapshot, self.stale_after_seconds)
            self.last_snapshot[index] = snapshot
            self.latest[index] = self._apply_trade_desk(index, snapshot, result)
        return dict(self.latest)

    async def run_forever(self, interval_seconds: int = 5, stop_event: asyncio.Event | None = None) -> None:
        while stop_event is None or not stop_event.is_set():
            self.cycle_once()
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=max(1, interval_seconds)
                ) if stop_event else await asyncio.sleep(max(1, interval_seconds))
            except asyncio.TimeoutError:
                continue
