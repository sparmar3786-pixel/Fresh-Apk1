from types import SimpleNamespace
import time

import pytest

from backend.app.live_execution import (
    LIVE_CONFIRMATION,
    LiveExecutionError,
    LiveExecutionService,
)


class FakeStore:
    def __init__(self, tick=None):
        self.tick = tick

    def get(self, token):
        return self.tick


class FakeMaster:
    rows = [1]

    def load_cache(self):
        return True

    def option_rows(self, index):
        return [{
            "name": index,
            "symbol": "NIFTY26OCT25000CE",
            "token": "12345",
            "exch_seg": "NFO",
            "instrumenttype": "OPTIDX",
            "strike": "2500000",
            "lotsize": "75",
        }]


class FakeClient:
    def __init__(self):
        self.placed = []

    def placeOrder(self, params):
        self.placed.append(params)
        return {"status": True, "data": {"orderid": "ANGEL-ORDER-1"}}


class FakeGateway:
    authenticated = True
    stream_open = True
    websocket_tick_count = 25

    def __init__(self):
        self.client = FakeClient()

    def status(self):
        return {"last_tick_age_seconds": 0.1}

    def positions(self):
        return {"status": True, "data": []}


def _signal(decision="CALL BUY", side="CE", guards=None):
    return SimpleNamespace(
        decision=decision,
        option_side=side,
        strike=25000,
        guards=guards or [],
        stop_loss=90.0,
        target=120.0,
    )


def _execute(service, gateway, **overrides):
    args = {
        "gateway": gateway,
        "master": FakeMaster(),
        "store": FakeStore({
            "received_at": time.time(),
            "source": "angel-one-websocket",
            "best_ask": 100.0,
            "last_traded_price": 99.5,
        }),
        "index": "NIFTY",
        "lots": 1,
        "confirmation": LIVE_CONFIRMATION,
        "request_id": "test-request-123",
        "stale_after_seconds": 15,
        "signal": _signal(),
    }
    args.update(overrides)
    return service.execute_qualified_signal(**args)


def test_live_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRESH_LIVE_TRADING_ENABLED", raising=False)
    service = LiveExecutionService()
    with pytest.raises(LiveExecutionError, match="disabled"):
        _execute(service, FakeGateway())


def test_wrong_confirmation_never_places_order(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    gateway = FakeGateway()
    with pytest.raises(LiveExecutionError, match="confirmation"):
        _execute(LiveExecutionService(), gateway, confirmation="YES")
    assert gateway.client.placed == []


def test_qualified_signal_places_real_angel_limit_order(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    gateway = FakeGateway()
    result = _execute(LiveExecutionService(), gateway)
    assert result["status"] == "SUBMITTED"
    assert result["order_id"] == "ANGEL-ORDER-1"
    assert result["quantity"] == 75
    assert gateway.client.placed[0]["transactiontype"] == "BUY"
    assert gateway.client.placed[0]["ordertype"] == "LIMIT"
    assert gateway.client.placed[0]["exchange"] == "NFO"


def test_stale_quote_blocks_real_order(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    gateway = FakeGateway()
    with pytest.raises(LiveExecutionError, match="stale"):
        _execute(
            LiveExecutionService(), gateway,
            store=FakeStore({
                "received_at": time.time() - 60,
                "source": "angel-one-websocket",
                "best_ask": 100.0,
                "last_traded_price": 99.5,
            }),
        )
    assert gateway.client.placed == []


def test_strategy_guard_blocks_order(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    gateway = FakeGateway()
    with pytest.raises(LiveExecutionError, match="guards"):
        _execute(LiveExecutionService(), gateway, signal=_signal(guards=["STALE_DATA"]))
    assert gateway.client.placed == []


def test_duplicate_request_id_does_not_submit_twice(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    service = LiveExecutionService()
    gateway = FakeGateway()
    first = _execute(service, gateway)
    second = _execute(service, gateway)
    assert first["order_id"] == second["order_id"]
    assert second["duplicate_request"] is True
    assert len(gateway.client.placed) == 1


def test_live_order_rejects_rest_fallback_quote(monkeypatch):
    monkeypatch.setenv("FRESH_LIVE_TRADING_ENABLED", "true")
    gateway = FakeGateway()
    with pytest.raises(LiveExecutionError, match="WebSocket"):
        _execute(
            LiveExecutionService(), gateway,
            store=FakeStore({
                "received_at": time.time(),
                "source": "angel-one-rest-fallback",
                "best_ask": 100.0,
                "last_traded_price": 99.5,
            }),
        )
    assert gateway.client.placed == []
