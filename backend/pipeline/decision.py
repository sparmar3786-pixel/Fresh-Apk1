from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.models import TradeDecision


@dataclass
class PipelineDecision:
    index: str
    verdict: TradeDecision = TradeDecision.WAIT
    plans: list[dict[str, Any]] = field(default_factory=list)
    plans_qualifying: int = 0
    plans_suppressed: int = 0
    suppression_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    override: str = "NONE"
    override_reason: str = ""
    confidence: float = 0.0
    regime: str | None = None
    data_quality: dict[str, Any] | None = None
    ai_summary: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {
            "index": self.index,
            "verdict": self.verdict.value,
            "plans": self.plans,
            "plans_qualifying": self.plans_qualifying,
            "plans_suppressed": self.plans_suppressed,
            "suppression_reasons": self.suppression_reasons,
            "notes": self.notes,
            "override": self.override,
            "override_reason": self.override_reason,
            "confidence": self.confidence,
            "regime": self.regime,
            "data_quality": self.data_quality,
            "ai_summary": self.ai_summary,
        }
