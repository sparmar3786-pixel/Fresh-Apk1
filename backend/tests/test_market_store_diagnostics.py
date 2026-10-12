from backend.app.market_store import MarketStore


def test_market_store_counts_updates_not_only_unique_tokens():
    store = MarketStore()
    store.update({"token": "NIFTY", "last_traded_price": 25000})
    store.update({"token": "NIFTY", "last_traded_price": 25001})
    store.update({"token": "CE1", "last_traded_price": 100})
    diag = store.diagnostics()
    assert diag["unique_tokens"] == 2
    assert diag["update_count"] == 3
    assert diag["last_update_age_seconds"] is not None
