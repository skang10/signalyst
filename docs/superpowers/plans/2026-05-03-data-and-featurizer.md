# Data Layer + TimeSeriesFeaturizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data connectors (yfinance, FRED, EIA) and `TimeSeriesFeaturizer` that turns raw time series into a leakage-free tabular feature matrix for TabPFN.

**Architecture:** Three connector functions fetch raw `pd.Series` from external APIs; `TimeSeriesFeaturizer` aligns them to a common daily index via forward-fill (respecting publication lag), then computes rolling stats, lag features, and momentum for each signal. The output is a `pd.DataFrame` ready to pass as `X_train`/`X_test` to TabPFN.

**Tech Stack:** `pandas`, `numpy`, `yfinance`, `fredapi`, `httpx` (all already in `pyproject.toml`).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/src/data/connectors.py` | `fetch_price_series`, `fetch_fred_series`, `fetch_eia_inventory` |
| Modify | `backend/src/data/__init__.py` | Re-export public API |
| Create | `backend/src/featurizer/featurizer.py` | `TimeSeriesFeaturizer` class |
| Modify | `backend/src/featurizer/__init__.py` | Re-export public API |
| Create | `backend/tests/test_data_connectors.py` | Connector tests (mocked HTTP) |
| Create | `backend/tests/test_featurizer.py` | Featurizer tests (synthetic data) |
| Modify | `backend/src/config.py` | Add `eia_api_key: str = ""` |

---

## Task 1: Add EIA API key to Settings

**Files:**
- Modify: `backend/src/config.py`

- [ ] **Step 1: Add field to Settings**

Open `backend/src/config.py` and add `eia_api_key` after `fred_api_key`:

```python
    anthropic_api_key: str = ""
    fred_api_key: str = ""
    eia_api_key: str = ""
```

- [ ] **Step 2: Verify existing config test still passes**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add backend/src/config.py
git commit -m "feat: add eia_api_key to Settings"
```

---

## Task 2: yfinance connector

**Files:**
- Create: `backend/src/data/connectors.py`
- Create: `backend/tests/test_data_connectors.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_data_connectors.py`:

```python
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.connectors import fetch_price_series


def _make_yf_download_result(ticker: str, n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close_values = [80.0, 81.0, 79.5, 82.0, 83.5][:n]
    # yfinance returns a MultiIndex DataFrame when multiple tickers,
    # or a single-level DataFrame for one ticker
    df = pd.DataFrame({"Close": close_values}, index=dates)
    df.index.name = "Date"
    return df


def test_fetch_price_series_returns_named_series():
    with patch("src.data.connectors.yf.download") as mock_dl:
        mock_dl.return_value = _make_yf_download_result("CL=F")
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_data_connectors.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `connectors.py` doesn't exist yet.

- [ ] **Step 3: Create connectors.py with yfinance connector**

Create `backend/src/data/connectors.py`:

```python
import pandas as pd
import yfinance as yf


def fetch_price_series(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch daily adjusted close price for a yfinance ticker symbol."""
    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"No data returned for ticker {ticker!r}")
    series: pd.Series = raw["Close"].squeeze()
    series.name = ticker
    series.index = pd.DatetimeIndex(series.index).rename("date")
    return series
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_data_connectors.py::test_fetch_price_series_returns_named_series tests/test_data_connectors.py::test_fetch_price_series_raises_on_empty -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/connectors.py backend/tests/test_data_connectors.py
git commit -m "feat: add yfinance price series connector with tests"
```

---

## Task 3: FRED connector

**Files:**
- Modify: `backend/src/data/connectors.py`
- Modify: `backend/tests/test_data_connectors.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_data_connectors.py`:

```python
from src.data.connectors import fetch_fred_series


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_data_connectors.py::test_fetch_fred_series_returns_named_series -v
```

Expected: `ImportError` — `fetch_fred_series` not yet defined.

- [ ] **Step 3: Add FRED connector to connectors.py**

Append to `backend/src/data/connectors.py`:

```python
from fredapi import Fred


def fetch_fred_series(series_id: str, start: str, end: str, api_key: str) -> pd.Series:
    """Fetch a FRED time series by ID."""
    fred = Fred(api_key=api_key)
    series = fred.get_series(series_id, observation_start=start, observation_end=end)
    series.name = series_id
    series.index.name = "date"
    return series
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_data_connectors.py::test_fetch_fred_series_returns_named_series -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/connectors.py backend/tests/test_data_connectors.py
git commit -m "feat: add FRED series connector with tests"
```

---

## Task 4: EIA inventory connector

**Files:**
- Modify: `backend/src/data/connectors.py`
- Modify: `backend/tests/test_data_connectors.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_data_connectors.py`:

```python
from src.data.connectors import fetch_eia_inventory


def test_fetch_eia_inventory_returns_weekly_change():
    fake_rows = [
        {"period": "2024-01-05", "value": "450000"},
        {"period": "2024-01-12", "value": "448000"},
        {"period": "2024-01-19", "value": "452000"},
    ]
    with patch("src.data.connectors._eia_get") as mock_get:
        mock_get.return_value = fake_rows
        result = fetch_eia_inventory("2024-01-01", "2024-01-31", api_key="test")

    # First row is dropped (diff produces NaN for first element)
    assert isinstance(result, pd.Series)
    assert result.name == "eia_inventory_change"
    assert len(result) == 2
    assert result.iloc[0] == pytest.approx(-2000.0)  # 448000 - 450000
    assert result.index.name == "date"


def test_fetch_eia_inventory_raises_on_http_error():
    import httpx

    with patch("src.data.connectors._eia_get") as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            fetch_eia_inventory("2024-01-01", "2024-01-31", api_key="bad")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_data_connectors.py::test_fetch_eia_inventory_returns_weekly_change tests/test_data_connectors.py::test_fetch_eia_inventory_raises_on_http_error -v
```

Expected: `ImportError` — `fetch_eia_inventory` not yet defined.

- [ ] **Step 3: Add EIA connector to connectors.py**

Append to `backend/src/data/connectors.py`:

```python
import httpx


def _eia_get(start: str, end: str, api_key: str) -> list[dict]:
    """Isolated HTTP call — kept separate so tests can mock it cleanly."""
    resp = httpx.get(
        "https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
        params={
            "api_key": api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "facets[product][]": "EPC0",   # crude oil
            "facets[duoarea][]": "NUS",     # US total
            "facets[process][]": "SAE",     # ending stocks
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
    """Fetch EIA weekly US crude oil inventory *change* (thousand barrels).

    Returns week-over-week difference: positive = build, negative = draw.
    The first observation is dropped (diff produces NaN there).
    """
    rows = _eia_get(start, end, api_key)
    records = {row["period"]: float(row["value"]) for row in rows}
    level = pd.Series(records, name="eia_inventory_level")
    level.index = pd.DatetimeIndex(level.index).rename("date")
    level = level.sort_index()
    change = level.diff().dropna()
    change.name = "eia_inventory_change"
    return change
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_data_connectors.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/connectors.py backend/tests/test_data_connectors.py
git commit -m "feat: add EIA inventory connector with tests"
```

---

## Task 5: Wire up data __init__.py

**Files:**
- Modify: `backend/src/data/__init__.py`

- [ ] **Step 1: Export public API**

Open `backend/src/data/__init__.py` and replace its contents:

```python
from src.data.connectors import fetch_eia_inventory, fetch_fred_series, fetch_price_series

__all__ = ["fetch_eia_inventory", "fetch_fred_series", "fetch_price_series"]
```

- [ ] **Step 2: Verify imports work**

```bash
cd backend && uv run python -c "from src.data import fetch_price_series, fetch_fred_series, fetch_eia_inventory; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/src/data/__init__.py
git commit -m "feat: export data connectors from src.data"
```

---

## Task 6: TimeSeriesFeaturizer — alignment

**Files:**
- Create: `backend/src/featurizer/featurizer.py`
- Create: `backend/tests/test_featurizer.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_featurizer.py`:

```python
import numpy as np
import pandas as pd
import pytest

from src.featurizer.featurizer import TimeSeriesFeaturizer


def _daily_series(name: str, n: int = 100, start: str = "2020-01-01") -> pd.Series:
    rng = np.random.default_rng(42)
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.Series(rng.standard_normal(n).cumsum() + 100, index=dates, name=name)


def _weekly_series(name: str, n: int = 50, start: str = "2020-01-01") -> pd.Series:
    rng = np.random.default_rng(0)
    dates = pd.date_range(start, periods=n, freq="W")
    return pd.Series(rng.standard_normal(n).cumsum() + 50, index=dates, name=name)


def test_align_two_daily_series_preserves_length():
    f = TimeSeriesFeaturizer()
    s1 = _daily_series("a")
    s2 = _daily_series("b")
    aligned = f.align({"a": s1, "b": s2})
    assert isinstance(aligned, pd.DataFrame)
    assert list(aligned.columns) == ["a", "b"]
    assert len(aligned) == 100


def test_align_weekly_series_forward_fills_to_daily():
    f = TimeSeriesFeaturizer()
    weekly = _weekly_series("inventory")
    aligned = f.align({"inventory": weekly})
    # 50 weeks ≈ 350 days; check that the index is daily
    assert aligned.index.freq == "D" or (aligned.index[1] - aligned.index[0]).days == 1
    # No NaN — weekly values should be forward-filled to all weekdays
    assert aligned["inventory"].notna().all()


def test_align_no_future_leakage():
    """Values before first weekly observation should remain NaN (not back-filled)."""
    f = TimeSeriesFeaturizer()
    dates_daily = pd.date_range("2020-01-01", periods=10, freq="D")
    daily = pd.Series(range(10), index=dates_daily, name="price")
    # Weekly series starts 3 days after daily
    dates_weekly = pd.date_range("2020-01-04", periods=5, freq="W")
    weekly = pd.Series(range(5), index=dates_weekly, name="inventory")
    aligned = f.align({"price": daily, "inventory": weekly})
    # Rows before the first weekly obs should have NaN for inventory
    assert aligned.loc[aligned.index < dates_weekly[0], "inventory"].isna().all()


def test_align_empty_dict_returns_empty_dataframe():
    f = TimeSeriesFeaturizer()
    result = f.align({})
    assert isinstance(result, pd.DataFrame)
    assert result.empty
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_featurizer.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create featurizer.py with align()**

Create `backend/src/featurizer/featurizer.py`:

```python
import pandas as pd


class TimeSeriesFeaturizer:
    def __init__(
        self,
        windows: list[int] | None = None,
        lags: list[int] | None = None,
    ):
        self.windows: list[int] = windows or [5, 20, 60]
        self.lags: list[int] = lags or [1, 5, 20]

    def align(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        """Align all series to a common daily index using forward-fill only.

        Uses ffill (not bfill) so no future values are introduced.
        """
        if not series_dict:
            return pd.DataFrame()

        all_dates = pd.DatetimeIndex(
            sorted({date for s in series_dict.values() for date in s.index})
        )
        daily_index = pd.date_range(start=all_dates.min(), end=all_dates.max(), freq="D")

        aligned = {
            name: series.reindex(daily_index, method="ffill")
            for name, series in series_dict.items()
        }
        return pd.DataFrame(aligned, index=daily_index)
```

- [ ] **Step 4: Run alignment tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_featurizer.py::test_align_two_daily_series_preserves_length tests/test_featurizer.py::test_align_weekly_series_forward_fills_to_daily tests/test_featurizer.py::test_align_no_future_leakage tests/test_featurizer.py::test_align_empty_dict_returns_empty_dataframe -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/featurizer/featurizer.py backend/tests/test_featurizer.py
git commit -m "feat: TimeSeriesFeaturizer.align with forward-fill and no-leakage guarantee"
```

---

## Task 7: TimeSeriesFeaturizer — rolling features

**Files:**
- Modify: `backend/src/featurizer/featurizer.py`
- Modify: `backend/tests/test_featurizer.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_featurizer.py`:

```python
def test_rolling_features_column_names():
    f = TimeSeriesFeaturizer(windows=[5, 20])
    s = _daily_series("wti", n=100)
    result = f._rolling_features(s, "wti")
    expected_cols = [
        "wti_mean_5d", "wti_std_5d", "wti_min_5d", "wti_max_5d",
        "wti_mean_20d", "wti_std_20d", "wti_min_20d", "wti_max_20d",
    ]
    assert sorted(result.columns.tolist()) == sorted(expected_cols)


def test_rolling_features_warmup_is_nan():
    """First (window-1) rows must be NaN — no partial-window values."""
    f = TimeSeriesFeaturizer(windows=[20], lags=[])
    s = _daily_series("wti", n=100)
    result = f._rolling_features(s, "wti")
    # Rows 0..18 (19 rows) should be NaN for window=20
    assert result["wti_mean_20d"].iloc[:19].isna().all()
    assert result["wti_mean_20d"].iloc[19:].notna().all()


def test_rolling_features_values_are_backward_looking():
    """The mean at row i must equal mean(values[i-w+1 : i+1])."""
    f = TimeSeriesFeaturizer(windows=[3])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], index=dates, name="x")
    result = f._rolling_features(s, "x")
    # At index 2 (third row), mean_3d = mean([1, 2, 3]) = 2.0
    assert result["x_mean_3d"].iloc[2] == pytest.approx(2.0)
    # At index 4, mean_3d = mean([3, 4, 5]) = 4.0
    assert result["x_mean_3d"].iloc[4] == pytest.approx(4.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_featurizer.py::test_rolling_features_column_names tests/test_featurizer.py::test_rolling_features_warmup_is_nan tests/test_featurizer.py::test_rolling_features_values_are_backward_looking -v
```

Expected: `AttributeError` — `_rolling_features` not yet defined.

- [ ] **Step 3: Add _rolling_features() to featurizer.py**

Append inside the `TimeSeriesFeaturizer` class in `backend/src/featurizer/featurizer.py`:

```python
    def _rolling_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        frames: dict[str, pd.Series] = {}
        for w in self.windows:
            rolling = series.rolling(w, min_periods=w)
            frames[f"{name}_mean_{w}d"] = rolling.mean()
            frames[f"{name}_std_{w}d"] = rolling.std()
            frames[f"{name}_min_{w}d"] = rolling.min()
            frames[f"{name}_max_{w}d"] = rolling.max()
        return pd.DataFrame(frames, index=series.index)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_featurizer.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/featurizer/featurizer.py backend/tests/test_featurizer.py
git commit -m "feat: add _rolling_features to TimeSeriesFeaturizer"
```

---

## Task 8: TimeSeriesFeaturizer — lag and momentum features

**Files:**
- Modify: `backend/src/featurizer/featurizer.py`
- Modify: `backend/tests/test_featurizer.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_featurizer.py`:

```python
def test_lag_features_shift_by_correct_amount():
    f = TimeSeriesFeaturizer(lags=[1, 3])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    s = pd.Series(range(10), index=dates, dtype=float, name="x")
    result = f._lag_features(s, "x")
    # x_lag_1d at row 3 should be value at row 2 (i.e. 2.0)
    assert result["x_lag_1d"].iloc[3] == pytest.approx(2.0)
    # x_lag_3d at row 5 should be value at row 2 (i.e. 2.0)
    assert result["x_lag_3d"].iloc[5] == pytest.approx(2.0)


def test_lag_features_first_rows_are_nan():
    f = TimeSeriesFeaturizer(lags=[5])
    s = _daily_series("x", n=20)
    result = f._lag_features(s, "x")
    assert result["x_lag_5d"].iloc[:5].isna().all()
    assert result["x_lag_5d"].iloc[5:].notna().all()


def test_momentum_features_column_names():
    f = TimeSeriesFeaturizer(windows=[5, 20])
    s = _daily_series("wti", n=100)
    result = f._momentum_features(s, "wti")
    assert sorted(result.columns.tolist()) == ["wti_roc_20d", "wti_roc_5d"]


def test_momentum_features_values():
    """roc_5d at row i = (value[i] - value[i-5]) / value[i-5]"""
    f = TimeSeriesFeaturizer(windows=[5])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    values = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0, 111.0, 112.0, 113.0, 114.0]
    s = pd.Series(values, index=dates, name="x")
    result = f._momentum_features(s, "x")
    # At row 5, roc_5d = (110 - 100) / 100 = 0.10
    assert result["x_roc_5d"].iloc[5] == pytest.approx(0.10)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_featurizer.py::test_lag_features_shift_by_correct_amount tests/test_featurizer.py::test_lag_features_first_rows_are_nan tests/test_featurizer.py::test_momentum_features_column_names tests/test_featurizer.py::test_momentum_features_values -v
```

Expected: `AttributeError` — `_lag_features` / `_momentum_features` not yet defined.

- [ ] **Step 3: Add _lag_features() and _momentum_features() to featurizer.py**

Append inside the `TimeSeriesFeaturizer` class:

```python
    def _lag_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_lag_{lag}d": series.shift(lag) for lag in self.lags},
            index=series.index,
        )

    def _momentum_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_roc_{w}d": series.pct_change(w) for w in self.windows},
            index=series.index,
        )
```

- [ ] **Step 4: Run all featurizer tests**

```bash
cd backend && uv run pytest tests/test_featurizer.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/featurizer/featurizer.py backend/tests/test_featurizer.py
git commit -m "feat: add lag and momentum features to TimeSeriesFeaturizer"
```

---

## Task 9: TimeSeriesFeaturizer — transform() end-to-end

**Files:**
- Modify: `backend/src/featurizer/featurizer.py`
- Modify: `backend/tests/test_featurizer.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_featurizer.py`:

```python
def test_transform_output_has_no_nan():
    f = TimeSeriesFeaturizer(windows=[5, 20], lags=[1, 5])
    s1 = _daily_series("wti", n=200)
    s2 = _weekly_series("inventory", n=80)
    result = f.transform({"wti": s1, "inventory": s2})
    assert isinstance(result, pd.DataFrame)
    assert not result.isna().any().any(), "transform() output must have no NaN"


def test_transform_includes_all_signal_features():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1])
    s1 = _daily_series("wti", n=100)
    s2 = _daily_series("gpr", n=100)
    result = f.transform({"wti": s1, "gpr": s2})
    cols = result.columns.tolist()
    # Each signal should contribute rolling, lag, and momentum columns
    assert any("wti_mean_5d" in c for c in cols)
    assert any("gpr_mean_5d" in c for c in cols)
    assert any("wti_lag_1d" in c for c in cols)
    assert any("wti_roc_5d" in c for c in cols)


def test_transform_temporal_ordering_preserved():
    """Output index must be monotonically increasing."""
    f = TimeSeriesFeaturizer(windows=[5], lags=[1])
    result = f.transform({"wti": _daily_series("wti", n=100)})
    assert result.index.is_monotonic_increasing
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_featurizer.py::test_transform_output_has_no_nan tests/test_featurizer.py::test_transform_includes_all_signal_features tests/test_featurizer.py::test_transform_temporal_ordering_preserved -v
```

Expected: `AttributeError` — `transform` not yet defined.

- [ ] **Step 3: Add transform() to featurizer.py**

Append inside the `TimeSeriesFeaturizer` class:

```python
    def transform(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        """Full pipeline: align → compute features → drop NaN rows."""
        aligned = self.align(series_dict)
        feature_frames = []
        for col in aligned.columns:
            s = aligned[col]
            feature_frames.append(self._rolling_features(s, col))
            feature_frames.append(self._lag_features(s, col))
            feature_frames.append(self._momentum_features(s, col))
        return pd.concat(feature_frames, axis=1).dropna()
```

- [ ] **Step 4: Run all featurizer tests**

```bash
cd backend && uv run pytest tests/test_featurizer.py -v
```

Expected: all 14 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/featurizer/featurizer.py backend/tests/test_featurizer.py
git commit -m "feat: add TimeSeriesFeaturizer.transform end-to-end pipeline"
```

---

## Task 10: Wire up featurizer __init__.py + run full test suite

**Files:**
- Modify: `backend/src/featurizer/__init__.py`

- [ ] **Step 1: Export public API**

Open `backend/src/featurizer/__init__.py` and replace its contents:

```python
from src.featurizer.featurizer import TimeSeriesFeaturizer

__all__ = ["TimeSeriesFeaturizer"]
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && uv run python -c "from src.featurizer import TimeSeriesFeaturizer; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass (no regressions against existing `test_health.py`, `test_config.py`, `test_routes.py`, `test_models.py`).

- [ ] **Step 4: Run linter**

```bash
cd backend && uv run ruff check src/data/ src/featurizer/ tests/test_data_connectors.py tests/test_featurizer.py
```

Expected: no errors.

- [ ] **Step 5: Final commit**

```bash
git add backend/src/featurizer/__init__.py
git commit -m "feat: export TimeSeriesFeaturizer from src.featurizer"
```

---

## Next Sessions (not today)

| Session | Focus |
|---|---|
| Session 2 | `src/inference/` — TabPFN classifier + regressor wrappers |
| Session 3 | `src/db/` — SQLModel run/history models + Alembic migration |
| Session 4 | `src/agent/` — tool definitions + ReAct loop using Anthropic SDK |
| Session 5 | Wire up API routes (replace 501s) + WebSocket Redis pub/sub |
| Session 6 | Frontend — RegimeDashboard + AgentStream components |
