from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.config import settings
from src.data.connectors import fetch_eia_inventory

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch weekly EIA crude oil inventory changes into context.signals."""
    api_key = settings.eia_api_key
    try:
        series = fetch_eia_inventory(
            context.date_range_start, context.date_range_end, api_key=api_key
        )
        context.signals["eia_inventory_change"] = series
        return {"fetched": {"eia_inventory_change": len(series)}, "skipped": []}
    except Exception as exc:
        return {"fetched": {}, "skipped": [f"eia_inventory_change: {exc}"]}
