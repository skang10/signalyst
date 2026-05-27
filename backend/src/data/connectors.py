from typing import Any

import httpx
import pandas as pd
import yfinance as yf
from fredapi import Fred


def fetch_price_series(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch daily adjusted close price for a yfinance ticker symbol.

    Args:
        ticker: yfinance symbol. Common ones:
                "CL=F"     — WTI crude oil (front-month futures)
                "BZ=F"     — Brent crude oil
                "DX-Y.NYB" — US Dollar Index (DXY)
                "XLE"      — Energy Select Sector ETF
                "SPY"      — S&P 500 ETF
        start:  start date, inclusive, ISO format "YYYY-MM-DD"
        end:    end date, exclusive, ISO format "YYYY-MM-DD"

    Returns:
        Daily pd.Series with DatetimeIndex named "date", series name = ticker.

    Raises:
        ValueError: if yfinance returns no data for the given ticker/range.

    Example:
        >>> s = fetch_price_series("CL=F", "2024-01-02", "2024-01-05")
        >>> s.name
        'CL=F'
        >>> s.index.name
        'date'
    """
    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"No data returned for ticker {ticker!r}")
    series = raw["Close"].squeeze()
    series.name = ticker
    series.index = pd.DatetimeIndex(series.index).rename("date")
    return series


def fetch_fred_series(series_id: str, start: str, end: str, api_key: str) -> pd.Series:
    """Fetch a FRED time series by ID.

    Args:
        series_id: FRED series ID. Common ones:
                   "INDPRO"   — Industrial Production Index (monthly)
                   "UNRATE"   — US Unemployment Rate (monthly)
                   "T10YIE"   — 10-Year Breakeven Inflation (daily)
                   "DTWEXBGS" — Trade-Weighted USD Index (daily)
        start:    start date, inclusive, ISO format "YYYY-MM-DD"
        end:      end date, inclusive, ISO format "YYYY-MM-DD"
        api_key:  FRED API key (free at https://fred.stlouisfed.org/docs/api/api_key.html)

    Returns:
        pd.Series at the series' native frequency (daily/monthly/etc.)
        with DatetimeIndex named "date", series name = series_id.

    Example:
        >>> s = fetch_fred_series("INDPRO", "2024-01-01", "2024-06-30", api_key="...")
        >>> s.name
        'INDPRO'
        >>> s.index.name
        'date'
    """
    fred = Fred(api_key=api_key)
    series = fred.get_series(series_id, observation_start=start, observation_end=end)
    series.name = series_id
    series.index.name = "date"
    return series


def _eia_get(start: str, end: str, api_key: str) -> list[dict[str, Any]]:
    """Isolated HTTP call — kept separate so tests can mock it cleanly."""
    resp = httpx.get(
        "https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
        params={
            "api_key": api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "facets[product][]": "EPC0",
            "facets[duoarea][]": "NUS",
            "facets[process][]": "SAE",
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": 5000,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["response"]["data"]  # type: ignore[no-any-return]


def fetch_eia_inventory(start: str, end: str, api_key: str) -> pd.Series:
    """Fetch EIA weekly US crude oil inventory change (thousand barrels).

    Pulls weekly ending stocks from the EIA v2 API and returns the
    week-over-week difference. Positive = inventory build (bearish),
    negative = inventory draw (bullish).

    Args:
        start:   start date, inclusive, ISO format "YYYY-MM-DD"
        end:     end date, inclusive, ISO format "YYYY-MM-DD"
        api_key: EIA API key (free at https://www.eia.gov/opendata/)

    Returns:
        Weekly pd.Series of inventory changes with DatetimeIndex named "date",
        series name = "eia_inventory_change". First raw observation is dropped
        (diff produces NaN there).

    Example:
        >>> s = fetch_eia_inventory("2024-01-01", "2024-06-30", api_key="...")
        >>> s.name
        'eia_inventory_change'
        >>> s.index.name
        'date'
        >>> # positive = build, negative = draw
        >>> s.iloc[0]  # e.g. -2000.0 means 2M barrel draw
        -2000.0
    """
    rows = _eia_get(start, end, api_key)
    records = {row["period"]: float(row["value"]) for row in rows}
    level = pd.Series(records, name="eia_inventory_level")
    level.index = pd.DatetimeIndex(level.index).rename("date")
    level = level.sort_index()
    change = level.diff().dropna()
    change.name = "eia_inventory_change"
    return change
