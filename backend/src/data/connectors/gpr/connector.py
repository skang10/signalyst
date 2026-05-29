from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.data.gpr import fetch_gpr_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch daily GPR index into context.signals['GPR']."""
    try:
        series = fetch_gpr_series(context.date_range_start, context.date_range_end)
        context.signals["GPR"] = series
        return {"fetched": {"GPR": len(series)}, "skipped": []}
    except Exception as exc:
        return {"fetched": {}, "skipped": [f"GPR: {exc}"]}
