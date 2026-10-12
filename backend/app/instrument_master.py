from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

INSTRUMENT_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
INDEX_ALIASES = {
    "NIFTY": {"name": {"NIFTY", "Nifty 50"}, "exchange": "NSE"},
    "BANKNIFTY": {"name": {"BANKNIFTY", "Nifty Bank"}, "exchange": "NSE"},
    "FINNIFTY": {"name": {"FINNIFTY", "Nifty Fin Service", "Nifty Financial Services"}, "exchange": "NSE"},
    "MIDCPNIFTY": {"name": {"MIDCPNIFTY", "NIFTY MID SELECT", "Nifty Midcap Select"}, "exchange": "NSE"},
    "SENSEX": {"name": {"SENSEX", "SENSEX 50"}, "exchange": "BSE"},
    "BANKEX": {"name": {"BANKEX"}, "exchange": "BSE"},
}


def _expiry_key(value: str) -> date | None:
    for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.title(), fmt).date()
        except ValueError:
            continue
    return None


class InstrumentMaster:
    def __init__(self, cache_path: str = "backend/data/scrip_master.json"):
        self.cache = Path(cache_path)
        self.rows: list[dict[str, Any]] = []

    async def sync(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.get(INSTRUMENT_URL)
                response.raise_for_status()
                rows = response.json()
            self.rows = rows
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps(rows), encoding="utf-8")
            return {"source": "live", "count": len(rows)}
        except Exception as exc:
            if self.cache.exists():
                self.rows = json.loads(self.cache.read_text(encoding="utf-8"))
                return {"source": "cache", "count": len(self.rows), "warning": str(exc)}
            raise RuntimeError("Instrument master unavailable and no cached copy exists") from exc

    def load_cache(self) -> bool:
        if not self.cache.exists():
            return False
        self.rows = json.loads(self.cache.read_text(encoding="utf-8"))
        return True

    def find_index(self, index: str) -> dict[str, Any] | None:
        spec = INDEX_ALIASES.get(index)
        if not spec:
            return None
        candidates = [
            r for r in self.rows
            if str(r.get("exch_seg", "")).upper() == spec["exchange"]
            and (str(r.get("name", "")) in spec["name"] or str(r.get("symbol", "")) in spec["name"])
        ]
        candidates.sort(key=lambda r: (str(r.get("instrumenttype", "")) != "AMXIDX", str(r.get("symbol", ""))))
        return candidates[0] if candidates else None

    def option_rows(self, index: str, as_of: date | None = None) -> list[dict[str, Any]]:
        spec = INDEX_ALIASES.get(index)
        if not spec:
            return []
        as_of = as_of or date.today()
        rows = []
        for row in self.rows:
            if str(row.get("name", "")) not in spec["name"]:
                continue
            if str(row.get("exch_seg", "")).upper() not in {"NFO", "BFO"}:
                continue
            if "OPT" not in str(row.get("instrumenttype", "")).upper():
                continue
            expiry = _expiry_key(str(row.get("expiry", "")))
            if expiry and expiry >= as_of:
                rows.append(row)
        if not rows:
            return []
        expiries = [_expiry_key(str(r.get("expiry", ""))) for r in rows]
        nearest = min((x for x in expiries if x), default=None)
        return [r for r in rows if _expiry_key(str(r.get("expiry", ""))) == nearest]
    def commodity_rows(self, as_of: date | None = None) -> list[dict[str, Any]]:
        """Return one nearest non-expired MCX futures contract per supported commodity."""
        as_of = as_of or date.today()
        roots = (
            "GOLD", "GOLDM", "SILVER", "SILVERM", "CRUDEOIL",
            "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD",
        )
        candidates: dict[str, list[dict[str, Any]]] = {root: [] for root in roots}
        for row in self.rows:
            if str(row.get("exch_seg", "")).upper() != "MCX":
                continue
            instrument_type = str(row.get("instrumenttype", "")).upper()
            if not instrument_type.startswith("FUT"):
                continue
            name = str(row.get("name", "")).upper().strip()
            symbol = str(row.get("symbol", "")).upper().strip()
            expiry = _expiry_key(str(row.get("expiry", "")))
            if not expiry or expiry < as_of:
                continue
            root = next((item for item in sorted(roots, key=len, reverse=True) if name == item or symbol.startswith(item)), None)
            if root:
                candidates[root].append(row)
        selected: list[dict[str, Any]] = []
        for root in roots:
            rows = candidates[root]
            rows.sort(key=lambda row: (
                _expiry_key(str(row.get("expiry", ""))) or date.max,
                str(row.get("symbol", "")),
            ))
            if rows:
                selected.append(rows[0])
        return selected

