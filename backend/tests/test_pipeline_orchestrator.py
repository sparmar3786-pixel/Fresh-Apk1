from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.app.models import MarketSnapshot
from backend.pipeline.base import PartResult
from backend.pipeline.context import PipelineSettings


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        index="NIFTY",
        exchange="NSE",
        ltp=22000,
        candles=[22000 + i * 2 for i in range(30)],
        options=[],
        timestamp=datetime.now(timezone.utc),
    )


def test_loader_registers_all_32_parts():
    from backend.pipeline import loader  # noqa: F401
    from backend.pipeline.base import registered_parts

    assert list(registered_parts()) == list(range(1, 33))


def test_orchestrator_executes_registered_parts_in_order():
    from backend.pipeline.orchestrator import TerminalEngine

    async def source(index: str):
        return _snapshot().model_copy(update={"index": index})

    engine = TerminalEngine(
        snapshot_provider=source,
        settings=PipelineSettings(),
    )

    async def run():
        result = await engine.run_cycle()
        assert result["NIFTY"]["parts"]
        assert [part["part"] for part in result["NIFTY"]["parts"]] == list(range(1, 33))

    asyncio.run(run())


def test_part_result_remains_serializable():
    result = PartResult(part=1, name="test", output={"ok": True})
    assert result.__dict__["part"] == 1
