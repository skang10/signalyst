from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data.gpr import _GPR_CACHE, fetch_gpr_series


def _excel_bytes(n_rows: int = 30) -> bytes:
    dates = pd.date_range("2023-01-01", periods=n_rows, freq="D")
    df = pd.DataFrame({"date": dates, "GPRD": np.linspace(80, 120, n_rows)})
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clear_cache():
    _GPR_CACHE.clear()
    yield
    _GPR_CACHE.clear()


def test_fetch_gpr_series_returns_series_named_gpr():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.httpx.get", return_value=mock_resp):
        result = fetch_gpr_series("2023-01-05", "2023-01-15")
    assert result.name == "GPR"
    assert isinstance(result.index, pd.DatetimeIndex)


def test_fetch_gpr_series_trims_to_date_range():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.httpx.get", return_value=mock_resp):
        result = fetch_gpr_series("2023-01-05", "2023-01-15")
    assert all(result.index >= pd.Timestamp("2023-01-05"))
    assert all(result.index <= pd.Timestamp("2023-01-15"))


def test_fetch_gpr_series_caches_on_first_call():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.httpx.get", return_value=mock_resp) as mock_get:
        fetch_gpr_series("2023-01-01", "2023-01-10")
        fetch_gpr_series("2023-01-01", "2023-01-10")
    assert mock_get.call_count == 1


def test_fetch_gpr_series_bypasses_stale_cache():
    stale_time = datetime.now() - timedelta(hours=25)
    _GPR_CACHE["gpr"] = (stale_time, pd.Series([], name="GPR", dtype=float))
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.httpx.get", return_value=mock_resp) as mock_get:
        fetch_gpr_series("2023-01-01", "2023-01-10")
    assert mock_get.call_count == 1


def test_fetch_gpr_series_raises_on_missing_gprd_column():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({"date": dates, "WRONG": [1, 2, 3, 4, 5]})
    buf = BytesIO()
    df.to_excel(buf, index=False)
    mock_resp = MagicMock()
    mock_resp.content = buf.getvalue()
    with (
        patch("src.data.gpr.httpx.get", return_value=mock_resp),
        pytest.raises(ValueError, match="schema"),
    ):
        fetch_gpr_series("2023-01-01", "2023-01-05")
