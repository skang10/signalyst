import pandas as pd

from scripts import demo


def test_sample_prediction_dates_prefers_dates_with_direction_predictions() -> None:
    assert hasattr(demo, "_sample_prediction_dates")

    regime_index = pd.date_range("2024-01-01", periods=30, freq="D")
    direction_index = regime_index[:-20]

    result = demo._sample_prediction_dates(regime_index, direction_index, n=10)

    assert list(result) == list(direction_index[-10:])


def test_sample_prediction_dates_falls_back_to_regime_dates_when_direction_is_empty() -> None:
    assert hasattr(demo, "_sample_prediction_dates")

    regime_index = pd.date_range("2024-01-01", periods=12, freq="D")
    direction_index = pd.DatetimeIndex([])

    result = demo._sample_prediction_dates(regime_index, direction_index, n=10)

    assert list(result) == list(regime_index[-10:])
