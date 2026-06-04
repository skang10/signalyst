from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
import yfinance as yf
from fastapi import APIRouter

from api.models import GprValue, IndicatorValue, MarketSnapshotResponse
from src.data.gpr import fetch_gpr_series

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


def _fetch_gpr() -> IndicatorValue | None:
    try:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=30)
        series = fetch_gpr_series(start.isoformat(), end.isoformat())
        if len(series) < 2:
            raise ValueError("insufficient GPR data")
        latest = round(float(series.iloc[-1]), 1)
        prev = float(series.iloc[-2])
        change_pct = round((latest - prev) / prev * 100, 2)
        return GprValue(value=latest, change_pct=change_pct)
    except Exception as exc:
        log.warning("market_snapshot.fetch_failed", ticker="GPR", error=str(exc))
        return None


@router.get("/market/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot() -> MarketSnapshotResponse:
    gpr = _fetch_gpr()
    snapshot = MarketSnapshotResponse(
        wti=_safe_fetch("CL=F"),
        brent=_safe_fetch("BZ=F"),
        dxy=_safe_fetch("DX-Y.NYB"),
        gpr=gpr,
        fetched_at=datetime.now(UTC).isoformat(),
    )
    log.debug(
        "market.snapshot",
        wti=snapshot.wti.price if snapshot.wti else None,
        brent=snapshot.brent.price if snapshot.brent else None,
        dxy=snapshot.dxy.price if snapshot.dxy else None,
        gpr=snapshot.gpr.value if snapshot.gpr else None,
    )
    return snapshot
