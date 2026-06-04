from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
import yfinance as yf
from fastapi import APIRouter

from api.models import IndicatorValue, MarketSnapshotResponse

router = APIRouter(tags=["market"])
log = structlog.get_logger()


def _fetch_price_change(ticker: str) -> dict:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=7)
    data = yf.download(
        ticker, start=start.isoformat(), end=end.isoformat(), progress=False, auto_adjust=True
    )
    if len(data) < 2:
        raise ValueError(f"insufficient data for {ticker}")
    close = data["Close"].squeeze()
    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change_pct = round((latest - prev) / prev * 100, 2)
    return {"price": round(latest, 2), "change_pct": change_pct}


def _safe_fetch(ticker: str) -> IndicatorValue | None:
    try:
        result = _fetch_price_change(ticker)
        return IndicatorValue(**result)
    except Exception as exc:
        log.warning("market_snapshot.fetch_failed", ticker=ticker, error=str(exc))
        return None


@router.get("/market/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot() -> MarketSnapshotResponse:
    return MarketSnapshotResponse(
        wti=_safe_fetch("CL=F"),
        brent=_safe_fetch("BZ=F"),
        dxy=_safe_fetch("DX-Y.NYB"),
        fetched_at=datetime.now(UTC).isoformat(),
    )
