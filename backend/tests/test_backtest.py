from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.eval.backtest import _annualised_sharpe, walk_forward_backtest


def _make_data(n: int = 300) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    np.random.seed(42)
    features = pd.DataFrame(np.random.randn(n, 5), index=dates, columns=[f"f{i}" for i in range(5)])
    wti = pd.Series(np.linspace(50, 80, n) + np.random.randn(n), index=dates, name="CL=F")
    spy = pd.Series(np.linspace(300, 400, n) + np.random.randn(n), index=dates, name="SPY")
    return features, wti, spy


def _mock_clf(default_label: str) -> MagicMock:
    clf = MagicMock()
    clf.fit.return_value = None
    clf.predict.side_effect = lambda X: pd.Series(default_label, index=X.index)
    return clf


def test_walk_forward_backtest_returns_required_keys():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert set(result.keys()) == {
        "regime_accuracy",
        "strategy_sharpe",
        "benchmark_sharpe",
        "n_windows",
        "date_range",
    }


def test_walk_forward_backtest_produces_multiple_windows():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert result["n_windows"] > 0


def test_walk_forward_backtest_sharpes_are_floats():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert isinstance(result["strategy_sharpe"], float)
    assert isinstance(result["benchmark_sharpe"], float)


def test_walk_forward_backtest_excludes_direction_labels_that_resolve_in_test_window():
    features, wti, spy = _make_data(n=60)
    observed_train_label_max_dates: list[pd.Timestamp] = []

    def direction_factory(*_args: object, **_kwargs: object) -> MagicMock:
        clf = _mock_clf("up")
        clf.fit.side_effect = lambda _X, y: observed_train_label_max_dates.append(y.index.max())
        return clf

    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", side_effect=direction_factory),
    ):
        walk_forward_backtest(features, wti, spy, horizon=5, step=20, min_train=20)

    assert observed_train_label_max_dates
    assert observed_train_label_max_dates[0] < features.index[20 - 5]


def test_walk_forward_backtest_scores_forward_horizon_returns():
    features, wti, spy = _make_data(n=40)
    wti = pd.Series(100.0, index=features.index, name="CL=F")
    spy = pd.Series(100.0, index=features.index, name="SPY")
    wti.iloc[15] = 110.0
    spy.iloc[15] = 105.0
    captured_returns: list[list[float]] = []

    def fake_sharpe(returns: list[float]) -> float:
        captured_returns.append(returns)
        return 0.0

    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
        patch("src.eval.backtest._annualised_sharpe", side_effect=fake_sharpe),
    ):
        walk_forward_backtest(features, wti, spy, horizon=5, step=20, min_train=10)

    assert captured_returns[0][0] == pytest.approx(0.10)
    assert captured_returns[1][0] == pytest.approx(0.05)


def test_walk_forward_backtest_respects_max_windows():
    features, wti, spy = _make_data(n=300)
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(
            features,
            wti,
            spy,
            horizon=20,
            step=20,
            min_train=120,
            max_windows=3,
        )

    assert result["n_windows"] == 3


def test_annualised_sharpe_zero_for_constant_returns():
    assert _annualised_sharpe([0.01, 0.01, 0.01]) == 0.0


def test_annualised_sharpe_positive_for_mostly_positive_returns():
    returns = [0.01] * 50 + [-0.001] * 5
    assert _annualised_sharpe(returns) > 0.0
