from __future__ import annotations

import datetime
from io import BytesIO

import httpx
import pandas as pd

from src.config import settings

_GPR_CACHE: dict[str, tuple[datetime.datetime, pd.Series]] = {}


def fetch_gpr_series(start: str, end: str) -> pd.Series:
    """Fetch daily GPR index from Matteo Iacoviello's page.

    Returns a pd.Series named 'GPR', DatetimeIndex named 'date', trimmed to [start, end].
    Results are cached in-process for `settings.gpr_cache_ttl_hours` hours.
    """
    now = datetime.datetime.now()
    ttl = datetime.timedelta(hours=settings.gpr_cache_ttl_hours)

    if "gpr" in _GPR_CACHE:
        cached_at, full_series = _GPR_CACHE["gpr"]
        if now - cached_at < ttl:
            return full_series.loc[pd.Timestamp(start) : pd.Timestamp(end)]

    response = httpx.get(settings.gpr_data_url, timeout=30)
    response.raise_for_status()

    try:
        df = pd.read_excel(BytesIO(response.content), engine="xlrd")
    except Exception as exc:
        if exc.__class__.__name__ != "XLRDError":
            raise
        df = pd.read_excel(BytesIO(response.content), engine="openpyxl")

    if not {"date", "GPRD"}.issubset(df.columns):
        raise ValueError(
            f"GPR data schema changed. Expected columns {{'date', 'GPRD'}}, got {set(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"])
    full_series = df.set_index("date")["GPRD"].rename("GPR")
    full_series.index.name = "date"

    _GPR_CACHE["gpr"] = (now, full_series)

    return full_series.loc[pd.Timestamp(start) : pd.Timestamp(end)]
