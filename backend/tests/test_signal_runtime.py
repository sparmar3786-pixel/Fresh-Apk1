from datetime import datetime, timezone

from backend.app.instrument_master import InstrumentMaster
from backend.app.market_store import MarketStore
from backend.app.signal_runtime import SignalRuntime, _timestamp


class FakeMaster:
    def find_index(self, index):
        return {"token": "IDX1", "symbol": index, "name": index, "exch_seg": "NSE"}

    def option_rows(self, index):
        return [
            {"token": "CE1", "symbol": index + "25000CE", "name": index, "strike": "2500000", "exch_seg": "NFO"},
            {"token": "PE1", "symbol": index + "25000PE", "name": index, "strike": "2500000", "exch_seg": "NFO"},
        ]


def test_runtime_builds_live_snapshot_from_latest_ticks():
    store = MarketStore()
    master = FakeMaster()
    runtime = SignalRuntime(master, store, indexes=["NIFTY"])
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    for i in range(25):
        store.update({
            "token": "IDX1",
            "last_traded_price": (25000 + i * 5) * 100,
            "exchange_timestamp": now_ms + i * 60_000,
        })
        store.update({
            "token": "CE1",
            "last_traded_price": 12000 + i * 50,
            "open_interest": 5000 + i * 20,
            "volume_trade_for_the_day": 1000 + i * 10,
            "exchange_timestamp": now_ms + i * 1000,
        })
        store.update({
            "token": "PE1",
            "last_traded_price": 9000 - i * 20,
            "open_interest": 4000 - i * 10,
            "volume_trade_for_the_day": 900 + i * 8,
            "exchange_timestamp": now_ms + i * 1000,
        })
        runtime.cycle_once()

    result = runtime.latest["NIFTY"]
    assert result.index == "NIFTY"
    assert result.strike == 25000
    assert result.option_side == "CE"
    assert result.entry is not None


def test_runtime_returns_no_trade_without_live_index_tick():
    store = MarketStore()
    runtime = SignalRuntime(FakeMaster(), store, indexes=["NIFTY"])
    runtime.cycle_once()
    assert runtime.latest["NIFTY"].decision.value == "NO TRADE"


def test_runtime_restores_last_snapshot_when_live_feed_is_unavailable():
    store = MarketStore()
    runtime = SignalRuntime(FakeMaster(), store, indexes=["NIFTY"])
    payload = {
        "index": "NIFTY",
        "exchange": "NSE",
        "ltp": 25000,
        "candles": [25000 + i for i in range(25)],
        "options": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "angel-one-live",
    }
    runtime.restore_snapshots({"NIFTY": payload})
    assert runtime.last_snapshot["NIFTY"].ltp == 25000
    assert "LIVE_FEED_UNAVAILABLE" in runtime.latest["NIFTY"].guards
    assert "last fetched market snapshot" in runtime.latest["NIFTY"].reason[0].lower()


def test_missing_tick_timestamp_is_not_replaced_with_current_time():
    missing = _timestamp({"token": "IDX1", "ltp": 25000})
    assert missing.year == 1970


def test_bad_exchange_timestamp_falls_back_to_receive_timestamp():
    received = 1_700_000_000
    stamp = _timestamp({"exchange_timestamp": "not-a-time", "received_at": received})
    assert stamp.timestamp() == received


def test_iso_exchange_timestamp_is_parsed():
    stamp = _timestamp({"exchange_timestamp": "2026-10-09T10:15:00+05:30"})
    assert stamp.isoformat() == "2026-10-09T04:45:00+00:00"
