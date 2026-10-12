"""Multi-provider news evidence for Fresh-Apk's AI signal filter.

Provider responses are treated as untrusted evidence, never as market prices or
trade instructions. Keys remain server-side; failures degrade to partial evidence.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import SearchEvidence


class SearchEvidenceService:
    def __init__(
        self,
        *,
        exa_key: str | None = None,
        tavily_key: str | None = None,
        brave_key: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.exa_key = (exa_key or "").strip()
        self.tavily_key = (tavily_key or "").strip()
        self.brave_key = (brave_key or "").strip()
        self.timeout_seconds = timeout_seconds

    @property
    def configured_providers(self) -> list[str]:
        return [
            name for name, key in (
                ("exa", self.exa_key), ("tavily", self.tavily_key), ("brave", self.brave_key)
            ) if key
        ]

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchEvidence]:
        query = " ".join((query or "").split())[:240]
        if not query or not self.configured_providers:
            return []
        limit = max(1, min(int(max_results), 5))
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            tasks = []
            if self.exa_key:
                tasks.append(self._exa(client, query, limit))
            if self.tavily_key:
                tasks.append(self._tavily(client, query, limit))
            if self.brave_key:
                tasks.append(self._brave(client, query, limit))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        combined: list[SearchEvidence] = []
        seen: set[str] = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            for item in result:
                normalized = self._canonical_url(item.url)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                combined.append(item)
        return combined[: limit * max(1, len(self.configured_providers))]

    async def _exa(self, client: httpx.AsyncClient, query: str, limit: int) -> list[SearchEvidence]:
        response = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self.exa_key, "Content-Type": "application/json"},
            json={"query": query, "type": "auto", "numResults": limit,
                  "contents": {"text": {"maxCharacters": 1200}}},
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        return [SearchEvidence(
            provider="exa", title=str(row.get("title") or "Untitled result")[:240],
            url=str(row.get("url") or ""), snippet=str(row.get("text") or "")[:1200],
            published_at=row.get("publishedDate") or row.get("published_date"),
        ) for row in rows if isinstance(row, dict) and row.get("url")]

    async def _tavily(self, client: httpx.AsyncClient, query: str, limit: int) -> list[SearchEvidence]:
        response = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": self.tavily_key, "query": query, "topic": "news",
                  "search_depth": "basic", "max_results": limit, "include_answer": False},
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        return [SearchEvidence(
            provider="tavily", title=str(row.get("title") or "Untitled result")[:240],
            url=str(row.get("url") or ""), snippet=str(row.get("content") or "")[:1200],
            published_at=row.get("published_date") or row.get("publishedDate"),
        ) for row in rows if isinstance(row, dict) and row.get("url")]

    async def _brave(self, client: httpx.AsyncClient, query: str, limit: int) -> list[SearchEvidence]:
        response = await client.get(
            "https://api.search.brave.com/res/v1/news/search",
            params={"q": query, "count": limit, "freshness": "pw"},
            headers={"X-Subscription-Token": self.brave_key, "Accept": "application/json"},
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        output = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("url"):
                continue
            meta = row.get("meta_url") if isinstance(row.get("meta_url"), dict) else {}
            output.append(SearchEvidence(
                provider="brave", title=str(row.get("title") or "Untitled result")[:240],
                url=str(row.get("url") or ""),
                snippet=str(row.get("description") or "")[:1200],
                published_at=row.get("age") or row.get("page_age") or meta.get("scheme"),
            ))
        return output

    @staticmethod
    def _canonical_url(url: str) -> str:
        try:
            parts = urlsplit(url.strip())
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                return ""
            host = parts.netloc.lower()
            path = parts.path.rstrip("/") or "/"
            # Remove tracking query and fragment for cross-provider deduplication.
            canonical = urlunsplit((parts.scheme.lower(), host, path, "", ""))
            return canonical if len(canonical) <= 2048 else ""
        except Exception:
            return ""

    @staticmethod
    def query_for_index(index: str) -> str:
        safe_index = " ".join((index or "").split())[:80]
        return f"{safe_index} India market news NSE BSE macroeconomic event"[:220]
