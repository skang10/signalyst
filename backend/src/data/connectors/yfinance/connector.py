from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.data.connectors import fetch_price_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch daily close price series for each ticker into context.signals."""
    tickers: list[str] = params["tickers"]
    fetched: dict[str, int] = {}
    skipped: list[str] = []

    for ticker in tickers:
        try:
            series = fetch_price_series(ticker, context.date_range_start, context.date_range_end)
            context.signals[ticker] = series
            fetched[ticker] = len(series)
        except Exception as exc:
            skipped.append(f"{ticker}: {exc}")

    return {"fetched": fetched, "skipped": skipped}
