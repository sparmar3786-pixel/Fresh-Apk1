from backend.app.search_evidence import SearchEvidenceService


def test_configured_providers_only_lists_nonempty_keys():
    service = SearchEvidenceService(exa_key=" key ", tavily_key="", brave_key=None)
    assert service.configured_providers == ["exa"]


def test_canonical_url_removes_tracking_query_and_fragment():
    canonical = SearchEvidenceService._canonical_url(
        "https://Example.com/story?id=123&utm_source=feed#section"
    )
    assert canonical == "https://example.com/story"


def test_canonical_url_rejects_non_http_urls():
    assert SearchEvidenceService._canonical_url("javascript:alert(1)") == ""
    assert SearchEvidenceService._canonical_url("not-a-url") == ""


def test_query_for_index_is_bounded_and_market_specific():
    query = SearchEvidenceService.query_for_index("  NIFTY   50  ")
    assert query == "NIFTY 50 India market news NSE BSE macroeconomic event"
    assert len(SearchEvidenceService.query_for_index("X" * 1000)) <= 220


def test_empty_query_or_missing_keys_returns_no_evidence():
    import asyncio

    service = SearchEvidenceService()
    assert asyncio.run(service.search("NIFTY")) == []
    assert asyncio.run(service.search("   ")) == []
