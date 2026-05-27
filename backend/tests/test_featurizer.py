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
    assert (aligned.index[1] - aligned.index[0]).days == 1
    assert aligned["inventory"].notna().all()


def test_align_no_future_leakage():
    f = TimeSeriesFeaturizer()
    dates_daily = pd.date_range("2020-01-01", periods=10, freq="D")
    daily = pd.Series(range(10), index=dates_daily, name="price")
    dates_weekly = pd.date_range("2020-01-04", periods=5, freq="W")
    weekly = pd.Series(range(5), index=dates_weekly, name="inventory")
    aligned = f.align({"price": daily, "inventory": weekly})
    assert aligned.loc[aligned.index < dates_weekly[0], "inventory"].isna().all()


def test_align_empty_dict_returns_empty_dataframe():
    f = TimeSeriesFeaturizer()
    result = f.align({})
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_rolling_features_column_names():
    f = TimeSeriesFeaturizer(windows=[5, 20])
    s = _daily_series("wti", n=100)
    result = f._rolling_features(s, "wti")
    expected_cols = [
        "wti_mean_5d",
        "wti_std_5d",
        "wti_min_5d",
        "wti_max_5d",
        "wti_mean_20d",
        "wti_std_20d",
        "wti_min_20d",
        "wti_max_20d",
    ]
    assert sorted(result.columns.tolist()) == sorted(expected_cols)


def test_rolling_features_warmup_is_nan():
    f = TimeSeriesFeaturizer(windows=[20], lags=[])
    s = _daily_series("wti", n=100)
    result = f._rolling_features(s, "wti")
    assert result["wti_mean_20d"].iloc[:19].isna().all()
    assert result["wti_mean_20d"].iloc[19:].notna().all()


def test_rolling_features_values_are_backward_looking():
    f = TimeSeriesFeaturizer(windows=[3])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], index=dates, name="x")
    result = f._rolling_features(s, "x")
    assert result["x_mean_3d"].iloc[2] == pytest.approx(2.0)
    assert result["x_mean_3d"].iloc[4] == pytest.approx(4.0)


def test_lag_features_shift_by_correct_amount():
    f = TimeSeriesFeaturizer(lags=[1, 3])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    s = pd.Series(range(10), index=dates, dtype=float, name="x")
    result = f._lag_features(s, "x")
    assert result["x_lag_1d"].iloc[3] == pytest.approx(2.0)
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
    f = TimeSeriesFeaturizer(windows=[5])
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    values = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0, 111.0, 112.0, 113.0, 114.0]
    s = pd.Series(values, index=dates, name="x")
    result = f._momentum_features(s, "x")
    assert result["x_roc_5d"].iloc[5] == pytest.approx(0.10)


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
    assert any("wti_mean_5d" in c for c in cols)
    assert any("gpr_mean_5d" in c for c in cols)
    assert any("wti_lag_1d" in c for c in cols)
    assert any("wti_roc_5d" in c for c in cols)


def test_transform_temporal_ordering_preserved():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1])
    result = f.transform({"wti": _daily_series("wti", n=100)})
    assert result.index.is_monotonic_increasing
