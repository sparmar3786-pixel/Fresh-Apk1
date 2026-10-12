"""Optional advanced option-flow / volatility-surface modules X378-X402.

The modules are deliberately data-gap safe: they only fire when the requested
inputs are actually supplied. They do not manufacture IV, order-flow, bid/ask,
or multi-expiry data from unrelated fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from backend.quant.option_math import clamp


FAMILY = "Advanced Optional"


@dataclass(frozen=True)
class AdvancedModule:
    strategy_id: str
    number: int
    name: str
    inputs: tuple[str, ...]
    formula: str
    required_data: tuple[str, ...]
    evaluator: Callable[[Mapping[str, Any]], tuple[float | None, dict[str, Any], str]]

    def evaluate(self, context: Mapping[str, Any], enabled: bool = True) -> dict[str, Any]:
        if not enabled:
            return {
                "strategy_id": self.strategy_id,
                "number": self.number,
                "name": self.name,
                "family": FAMILY,
                "fired": False,
                "data_gap": False,
                "advanced": True,
                "score": 0.0,
                "confidence": 0.0,
                "evidence": {},
                "reason": "advanced engine disabled",
            }
        score, evidence, reason = self.evaluator(context)
        if score is None:
            return {
                "strategy_id": self.strategy_id,
                "number": self.number,
                "name": self.name,
                "family": FAMILY,
                "fired": False,
                "data_gap": True,
                "advanced": True,
                "score": None,
                "confidence": 0.0,
                "evidence": evidence or {},
                "reason": reason or "required data missing",
            }
        score = float(clamp(score, -1.0, 1.0))
        return {
            "strategy_id": self.strategy_id,
            "number": self.number,
            "name": self.name,
            "family": FAMILY,
            "fired": abs(score) > 0.08,
            "data_gap": False,
            "advanced": True,
            "side": "CE" if score > 0 else "PE" if score < 0 else None,
            "score": round(score, 4),
            "confidence": round(abs(score), 4),
            "evidence": evidence or {},
            "reason": reason or ("fired" if abs(score) > 0.08 else "below threshold"),
        }


def _vs(c: Mapping[str, Any]) -> Mapping[str, Any]:
    return c.get("vol_surface") or {}


def _of(c: Mapping[str, Any]) -> Mapping[str, Any]:
    return c.get("order_flow") or {}


def _ml(c: Mapping[str, Any]) -> Mapping[str, Any]:
    return c.get("multi_leg") or {}


def _snap(c: Mapping[str, Any]):
    return c.get("snapshot")


def _scale(value: Any, multiplier: float) -> float | None:
    return None if value is None else clamp(float(value) * multiplier, -1.0, 1.0)


def _m378(c): v = _vs(c); return _scale(v.get("iv_slope"), -20), dict(v), "IV surface slope"
def _m379(c): v = _vs(c); return _scale(v.get("iv_curvature"), 20), dict(v), "IV surface curvature"
def _m380(c): v = _vs(c); return _scale(v.get("surface_shift"), 20), dict(v), "IV surface shift"
def _m381(c): v = _vs(c); return _scale(v.get("skew"), -20), dict(v), "IV smile/skew change"
def _m382(c): v = _vs(c); return _scale(v.get("otm_vs_atm_iv"), -20), dict(v), "ATM vs OTM IV divergence"


def _m383(c):
    ts = _vs(c).get("term_structure") or {}
    return _scale(ts.get("slope"), 10), dict(ts), "IV term-structure slope"


def _m384(c):
    ts = _vs(c).get("term_structure") or {}
    inv = ts.get("inverted")
    return (None if inv is None else (-0.4 if bool(inv) else 0.2)), dict(ts), "IV term-structure inversion"


def _m385(c): v = _vs(c); return (None if v.get("moneyness_iv_points") is None else clamp(float(v["moneyness_iv_points"]) / 40 - 0.3, -1, 1)), dict(v), "moneyness-IV interaction"
def _m386(c): o = _of(c); return _scale(o.get("vega_weighted_flow"), 10), dict(o), "vega-weighted net demand"
def _m387(c): o = _of(c); return _scale(o.get("vega_flow_acceleration"), 10), dict(o), "vega flow acceleration"
def _m388(c): o = _of(c); return _scale(o.get("vega_flow_reversal"), -10), dict(o), "vega flow reversal"


def _m389(c):
    o = _of(c); d, v = o.get("delta_weighted_flow"), o.get("vega_weighted_flow")
    return (None if d is None or v is None else clamp((float(d) - float(v)) * 10, -1, 1)), dict(o), "delta-vs-vega flow separation"


_m390 = _m389
def _m391(c): o = _of(c); return _scale(o.get("delta_weighted_flow"), 1), dict(o), "delta-informed flow"
def _m392(c): o = _of(c); return _scale(o.get("vega_weighted_flow"), 10), dict(o), "vega-informed flow"


def _m393(c):
    o = _of(c); d, v = o.get("flow_imbalance"), o.get("vega_weighted_flow")
    return (None if d is None else clamp(float(d), -1, 1)), {"direction": d, "volatility": v}, "direction/volatility information scores"


def _m394(c):
    o = _of(c); d, v = o.get("delta_weighted_flow"), o.get("vega_weighted_flow")
    return (None if d is None else clamp(float(d) + float(v or 0), -1, 1)), dict(o), "combined information imbalance"


def _m395(c):
    o = _of(c)
    return (None if o.get("data_gap") else clamp(float(o.get("flow_imbalance", 0)), -1, 1)), dict(o), "same-expiry cross-strike flow"


def _m396(c):
    snap = _snap(c)
    if snap is None:
        return None, {}, "option snapshot missing"
    ce = sum(float(o.volume or 0) for o in snap.options if o.side == "CE")
    pe = sum(float(o.volume or 0) for o in snap.options if o.side == "PE")
    total = ce + pe
    return (None if total == 0 else clamp((ce - pe) / total, -1, 1)), {"ce_volume": ce, "pe_volume": pe}, "same-strike CE/PE flow"


def _m397(c):
    return None, {"note": "multiple expiries are not present in MarketSnapshot"}, "cross-maturity flow requires multiple expiries"


def _m398(c): o = _of(c); return _scale(o.get("delta_weighted_flow"), 0.5), dict(o), "delta-bucket flow"
def _m399(c): o = _of(c); return _scale(o.get("vega_weighted_flow"), 5), dict(o), "vega-bucket flow"


def _m400(c):
    o = _of(c)
    if o.get("data_gap"):
        return None, dict(o), "order-flow data gap"
    return clamp((float(o.get("flow_imbalance", 0)) + float(o.get("persistence", 0))) / 2, -1, 1), dict(o), "aggregate option-flow pressure"


def _m401(c):
    ml = _ml(c)
    structures = ml.get("structures_recognized")
    return (None if structures is None else clamp(len(structures) / 23 - 0.2, -1, 1)), dict(ml), "multi-leg strategy recognition"


def _m402(c):
    o = _of(c)
    if o.get("data_gap"):
        return None, dict(o), "trade classification data gap"
    return clamp(float(o.get("flow_imbalance", 0)), -1, 1), dict(o), "trade classification engine"


_MODULES = [
    (378, "IV surface slope", ("iv", "option_chain"), "d(IV)/d(moneyness) slope", ("iv",), _m378),
    (379, "IV surface curvature", ("iv", "option_chain"), "second-order IV curvature", ("iv",), _m379),
    (380, "IV surface shift", ("iv",), "IV level change vs previous", ("iv",), _m380),
    (381, "IV smile/skew change", ("iv",), "change in smile/skew", ("iv",), _m381),
    (382, "ATM vs OTM IV divergence", ("iv", "option_chain"), "OTM IV - ATM IV", ("iv",), _m382),
    (383, "term-structure slope", ("iv", "expiries"), "IV term-structure slope", ("multi_expiry",), _m383),
    (384, "term-structure inversion", ("iv", "expiries"), "front IV > back IV", ("multi_expiry",), _m384),
    (385, "moneyness-IV interaction", ("iv", "strikes"), "IV by moneyness", ("iv",), _m385),
    (386, "vega-weighted net demand", ("volume", "vega"), "sum(volume*vega)", ("bid_ask",), _m386),
    (387, "vega flow acceleration", ("volume", "vega"), "d(vega flow)/dt", ("bid_ask",), _m387),
    (388, "vega flow reversal", ("volume", "vega"), "sign flip in vega flow", ("bid_ask",), _m388),
    (389, "delta-vs-vega flow separation", ("volume", "delta", "vega"), "delta flow vs vega flow", ("bid_ask",), _m389),
    (390, "directional-flow vs-volatility-flow separation", ("volume", "delta", "vega"), "direction vs vol flow", ("bid_ask",), _m390),
    (391, "delta-informed flow", ("volume", "delta"), "delta-weighted aggressor flow", ("bid_ask",), _m391),
    (392, "vega-informed flow", ("volume", "vega"), "vega-weighted aggressor flow", ("bid_ask",), _m392),
    (393, "direction/volatility information scores", ("volume",), "info scores", ("bid_ask",), _m393),
    (394, "combined information imbalance", ("volume",), "combined imbalance", ("bid_ask",), _m394),
    (395, "same-expiry cross-strike flow", ("volume", "strikes"), "flow across strikes", ("bid_ask",), _m395),
    (396, "same-strike CE/PE flow", ("volume",), "CE vs PE flow", ("volume",), _m396),
    (397, "cross-maturity flow", ("volume", "expiries"), "flow across expiries", ("multi_expiry",), _m397),
    (398, "delta-bucket flow", ("volume", "delta"), "flow by delta bucket", ("bid_ask",), _m398),
    (399, "vega-bucket flow", ("volume", "vega"), "flow by vega bucket", ("bid_ask",), _m399),
    (400, "aggregate option-flow pressure", ("volume",), "net flow pressure", ("bid_ask",), _m400),
    (401, "multi-leg strategy recognition", ("strikes", "premium"), "structure recognition", ("option_chain",), _m401),
    (402, "trade classification engine", ("volume", "bid_ask"), "aggressor classification", ("bid_ask",), _m402),
]


def build_advanced() -> list[AdvancedModule]:
    return [
        AdvancedModule(
            strategy_id=f"X{num:03d}",
            number=num,
            name=name,
            inputs=tuple(inputs),
            formula=formula,
            required_data=tuple(required_data),
            evaluator=fn,
        )
        for num, name, inputs, formula, required_data, fn in _MODULES
    ]


def run_advanced(context: Mapping[str, Any], enabled: bool = True) -> list[dict[str, Any]]:
    """Evaluate all 25 optional modules without inventing missing data."""
    return [module.evaluate(context, enabled=enabled) for module in build_advanced()]


ADVANCED_COUNT = len(_MODULES)
