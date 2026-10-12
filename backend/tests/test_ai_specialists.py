from backend.app.ai import _normalize_agent_analysis


def test_missing_news_history_and_portfolio_are_never_claimed_as_available():
    brief = {
        "agent_ensemble": {
            "agents": {
                "sentiment_analyst": {"status": "UNAVAILABLE", "direction": "UNKNOWN"},
                "reflection_analyst": {"status": "UNAVAILABLE"},
                "portfolio_manager": {"status": "UNAVAILABLE"},
            }
        },
        "decision_context": {"hard_guards": []},
    }
    result = _normalize_agent_analysis(
        {
            "agent_analysis": {
                "sentiment": {"status": "AVAILABLE", "view": "BULLISH", "rationale": "guessed"},
                "reflection": {"status": "AVAILABLE", "lessons": ["guessed lesson"]},
                "portfolio_manager": {"status": "AVAILABLE", "exposure_notes": ["guessed exposure"]},
            }
        },
        brief,
        evidence_count=0,
    )
    agents = result["specialists"]
    assert agents["sentiment"]["status"] == "UNAVAILABLE"
    assert agents["sentiment"]["view"] == "UNKNOWN"
    assert agents["reflection"]["status"] == "UNAVAILABLE"
    assert agents["reflection"]["lessons"] == []
    assert agents["portfolio_manager"]["status"] == "UNAVAILABLE"
    assert agents["portfolio_manager"]["exposure_notes"] == []
    assert result["separate_provider_models"] is False


def test_hard_guards_force_risk_agent_to_block():
    result = _normalize_agent_analysis(
        {"agent_analysis": {"risk_auditor": {"status": "CLEAR", "verdict": "CALL BUY", "flags": []}}},
        {"decision_context": {"hard_guards": ["STALE_SNAPSHOT"]}},
        evidence_count=0,
    )
    risk = result["specialists"]["risk_auditor"]
    assert risk["status"] == "BLOCKED"
    assert risk["verdict"] == "NO TRADE"
    assert "STALE_SNAPSHOT" in risk["flags"]


def test_deterministic_specialist_fallbacks_survive_empty_llm_sections():
    result = _normalize_agent_analysis(
        {"agent_analysis": {}},
        {"agent_ensemble": {"agents": {"quant_analyst": {"status": "AVAILABLE", "direction": "BEARISH"}}}},
        evidence_count=0,
    )
    report = result["specialists"]["technical_quant"]
    assert report["deterministic_status"] == "AVAILABLE"
    assert report["deterministic_direction"] == "BEARISH"
