from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from src.data.connectors import fetch_fred_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch FRED macro series into context.signals."""
    series_ids: list[str] = params["series_ids"]
    api_key = os.environ.get("FRED_API_KEY", "")
    fetched: dict[str, int] = {}
    skipped: list[str] = []

    for series_id in series_ids:
        try:
            series = fetch_fred_series(
                series_id, context.date_range_start, context.date_range_end, api_key=api_key
            )
            context.signals[series_id] = series
            fetched[series_id] = len(series)
        except Exception as exc:
            skipped.append(f"{series_id}: {exc}")

    return {"fetched": fetched, "skipped": skipped}
