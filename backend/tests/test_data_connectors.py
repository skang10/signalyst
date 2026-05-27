from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.connectors import fetch_fred_series, fetch_price_series


def _make_yf_result(n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({"Close": [80.0, 81.0, 79.5, 82.0, 83.5][:n]}, index=dates)
    df.index.name = "Date"
    return df


def test_fetch_price_series_returns_named_series():
    with patch("src.data.connectors.yf.download") as mock_dl:
        mock_dl.return_value = _make_yf_result()
        result = fetch_price_series("CL=F", "2024-01-01", "2024-01-05")

    assert isinstance(result, pd.Series)
    assert result.name == "CL=F"
    assert len(result) == 5
    assert result.index.name == "date"


def test_fetch_price_series_raises_on_empty():
    with patch("src.data.connectors.yf.download") as mock_dl:
        mock_dl.return_value = pd.DataFrame()
        with pytest.raises(ValueError, match="No data returned"):
            fetch_price_series("FAKE", "2024-01-01", "2024-01-05")


def test_fetch_fred_series_returns_named_series():
    with patch("src.data.connectors.Fred") as MockFred:
        instance = MockFred.return_value
        dates = pd.date_range("2024-01-01", periods=4, freq="ME")
        instance.get_series.return_value = pd.Series(
            [52.1, 51.8, 53.0, 52.5], index=dates, name="ISM/MAN_PMI"
        )
        result = fetch_fred_series("ISM/MAN_PMI", "2024-01-01", "2024-04-30", api_key="test")

    assert isinstance(result, pd.Series)
    assert result.name == "ISM/MAN_PMI"
    assert result.index.name == "date"
    MockFred.assert_called_once_with(api_key="test")


def test_fetch_eia_inventory_returns_weekly_change():
    from src.data.connectors import fetch_eia_inventory

    fake_rows = [
        {"period": "2024-01-05", "value": "450000"},
        {"period": "2024-01-12", "value": "448000"},
        {"period": "2024-01-19", "value": "452000"},
    ]
    with patch("src.data.connectors._eia_get") as mock_get:
        mock_get.return_value = fake_rows
        result = fetch_eia_inventory("2024-01-01", "2024-01-31", api_key="test")

    assert isinstance(result, pd.Series)
    assert result.name == "eia_inventory_change"
    assert len(result) == 2
    assert result.iloc[0] == pytest.approx(-2000.0)
    assert result.index.name == "date"


def test_fetch_eia_inventory_raises_on_http_error():
    import httpx

    from src.data.connectors import fetch_eia_inventory

    with patch("src.data.connectors._eia_get") as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            fetch_eia_inventory("2024-01-01", "2024-01-31", api_key="bad")
