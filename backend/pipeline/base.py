from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class PartResult:
    part: int
    name: str
    ok: bool = True
    data_gap: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    skipped: bool = False

_REGISTRY: dict[int, Callable] = {}
REGISTRY = _REGISTRY
PART_NAMES: dict[int, str] = {}

def register(number: int):
    def deco(fn):
        _REGISTRY[number] = fn
        PART_NAMES[number] = fn.__name__
        return fn
    return deco

def registered_parts():
    return dict(sorted(_REGISTRY.items()))
