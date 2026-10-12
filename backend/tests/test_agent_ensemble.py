from types import SimpleNamespace

from backend.app.agent_ensemble import build_agent_ensemble


def test_agent_ensemble_reports_specialists_and_does_not_invent_sentiment():
    snapshot = SimpleNamespace(options=[
        SimpleNamespace(side="CE", oi_change=10, premium_change=2),
        SimpleNamespace(side="PE", oi_change=4, premium_change=-1),
    ])
    strategy = SimpleNamespace(
        decision="CALL BUY", regime="BULLISH", guards=[],
        indicators={"ema_fast": 105, "ema_slow": 100, "macd_hist": 0.5, "rsi14": 62},
        entry=100, stop_loss=90, target=120,
    )
    result = build_agent_ensemble(snapshot, strategy, {"hard_guards": []}, [])
    assert result["agents"]["quant_analyst"]["direction"] == "BULLISH"
    assert result["agents"]["options_flow_analyst"]["status"] == "AVAILABLE"
    assert result["agents"]["sentiment_analyst"]["status"] == "UNAVAILABLE"
    assert result["agents"]["portfolio_manager"]["status"] == "UNAVAILABLE"
    assert result["consensus"] == "BULLISH"


def test_agent_ensemble_hard_guard_forces_no_trade_consensus():
    strategy = SimpleNamespace(
        decision="CALL BUY", regime="BULLISH", guards=["STALE_DATA"],
        indicators={}, entry=None, stop_loss=None, target=None,
    )
    result = build_agent_ensemble(None, strategy, {"hard_guards": []}, [])
    assert result["hard_block"] is True
    assert result["consensus"] == "NO TRADE"
    assert "STALE_DATA" in result["agents"]["risk_auditor"]["blocks"]


def test_agent_ensemble_marks_conflicting_directional_agents():
    snapshot = SimpleNamespace(options=[
        SimpleNamespace(side="PE", oi_change=10, premium_change=2),
    ])
    strategy = SimpleNamespace(
        decision="CALL BUY", regime="BULLISH", guards=[],
        indicators={"ema_fast": 105, "ema_slow": 100, "macd_hist": 0.5},
        entry=100, stop_loss=90, target=120,
    )
    result = build_agent_ensemble(snapshot, strategy, {}, [])
    assert result["agents"]["options_flow_analyst"]["direction"] == "BEARISH"
    assert result["consensus"] == "CONFLICT"


def test_sentiment_report_exposes_source_diversity_and_does_not_claim_trained_model():
    snapshot = SimpleNamespace(options=[])
    strategy = SimpleNamespace(
        decision="WAIT", regime="MIXED", guards=[], indicators={},
        entry=None, stop_loss=None, target=None,
    )
    evidence = [
        SimpleNamespace(provider="exa", url="https://www.example.com/a?track=1",
                        title="Company beats estimates", snippet="strong growth", published_at="2026-10-09"),
        SimpleNamespace(provider="brave", url="https://news.example.org/b",
                        title="Market downgrade", snippet="weak demand", published_at=None),
    ]
    result = build_agent_ensemble(snapshot, strategy, {}, evidence)
    report = result["agents"]["sentiment_analyst"]
    assert report["status"] == "PARTIAL"
    assert report["provider_count"] == 2
    assert report["unique_domain_count"] == 2
    assert report["dated_evidence_count"] == 1
    assert report["undated_evidence_count"] == 1
    assert report["lexical_polarity_hint"] == "MIXED_OR_NEUTRAL"
    assert "not a trained sentiment model" in report["warning"]


def test_sentiment_evidence_is_context_only_and_cannot_clear_hard_guard():
    snapshot = SimpleNamespace(options=[])
    strategy = SimpleNamespace(
        decision="CALL BUY", regime="BULLISH", guards=["STALE_DATA"],
        indicators={"ema_fast": 110, "ema_slow": 100, "macd_hist": 1},
        entry=100, stop_loss=90, target=120,
    )
    evidence = [SimpleNamespace(provider="exa", url="https://example.com/news",
                                title="Bullish rally beats estimates", snippet="strong growth",
                                published_at="2026-10-09")]
    result = build_agent_ensemble(snapshot, strategy, {}, evidence)
    assert result["agents"]["sentiment_analyst"]["lexical_polarity_hint"] == "POSITIVE_LEXICAL_HINT"
    assert result["hard_block"] is True
    assert result["consensus"] == "NO TRADE"
