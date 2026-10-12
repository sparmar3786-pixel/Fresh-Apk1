from backend.app.market_store import MarketStore


def test_market_store_keeps_latest_tick_per_token():
    store = MarketStore()
    store.update({"token": "1", "last_traded_price": 100})
    store.update({"token": "1", "last_traded_price": 101})
    assert store.get("1")["last_traded_price"] == 101
    assert len(store.snapshot()) == 1
