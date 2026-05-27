from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import NotFittedError

from src.inference.classifier import DirectionClassifier, OilRegimeClassifier


def _feature_df(n: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        rng.standard_normal((n, 5)),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )


def _regime_labels(n: int = 10) -> pd.Series:
    labels = (
        ["bull_supercycle"] * 3 + ["range_bound"] * 3 + ["bust"] * 2 + ["geopolitical_spike"] * 2
    )[:n]
    return pd.Series(labels, name="regime")


def _mock_clf(classes: list[str], proba: list[list[float]]) -> MagicMock:
    mock = MagicMock()
    mock.classes_ = np.array(classes)
    mock.predict_proba.return_value = np.array(proba)
    mock.predict.return_value = np.array([classes[int(np.argmax(row))] for row in proba])
    return mock


REGIME_CLASSES = ["bull_supercycle", "bust", "geopolitical_spike", "range_bound"]
REGIME_PROBA = [
    [0.6, 0.1, 0.2, 0.1],
    [0.1, 0.7, 0.1, 0.1],
    [0.2, 0.1, 0.5, 0.2],
]


def test_regime_predict_returns_series_with_correct_index():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(3))
        result = clf.predict(X)

    assert isinstance(result, pd.Series)
    assert result.name == "regime"
    assert list(result.index) == list(X.index)


def test_regime_predict_returns_correct_labels():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(3))
        result = clf.predict(X)

    assert result.iloc[0] == "bull_supercycle"
    assert result.iloc[1] == "bust"
    assert result.iloc[2] == "geopolitical_spike"


def test_regime_predict_proba_columns_match_classes():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(3))
        result = clf.predict_proba(X)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == REGIME_CLASSES
    assert list(result.index) == list(X.index)


def test_regime_predict_proba_values():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(3))
        result = clf.predict_proba(X)

    assert result.iloc[0]["bull_supercycle"] == pytest.approx(0.6)
    assert result.iloc[1]["bust"] == pytest.approx(0.7)


def test_regime_raises_not_fitted_on_predict():
    with patch("src.inference.classifier.TabPFNClassifier"):
        clf = OilRegimeClassifier()
        with pytest.raises(NotFittedError):
            clf.predict(_feature_df(3))


def test_regime_raises_not_fitted_on_predict_proba():
    with patch("src.inference.classifier.TabPFNClassifier"):
        clf = OilRegimeClassifier()
        with pytest.raises(NotFittedError):
            clf.predict_proba(_feature_df(3))


DIR_CLASSES = ["down", "up"]
DIR_PROBA = [
    [0.3, 0.7],
    [0.8, 0.2],
    [0.45, 0.55],
]


def test_direction_predict_returns_series_with_correct_index():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(DIR_CLASSES, DIR_PROBA)
        clf = DirectionClassifier()
        clf.fit(X, pd.Series(["up", "down", "up"]))
        result = clf.predict(X)

    assert isinstance(result, pd.Series)
    assert result.name == "direction"
    assert list(result.index) == list(X.index)


def test_direction_predict_returns_up_or_down():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(DIR_CLASSES, DIR_PROBA)
        clf = DirectionClassifier()
        clf.fit(X, pd.Series(["up", "down", "up"]))
        result = clf.predict(X)

    assert set(result.unique()).issubset({"up", "down"})
    assert result.iloc[0] == "up"
    assert result.iloc[1] == "down"


def test_direction_predict_proba_has_two_columns():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(DIR_CLASSES, DIR_PROBA)
        clf = DirectionClassifier()
        clf.fit(X, pd.Series(["up", "down", "up"]))
        result = clf.predict_proba(X)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["down", "up"]
    assert list(result.index) == list(X.index)


def test_direction_raises_not_fitted():
    with patch("src.inference.classifier.TabPFNClassifier"):
        clf = DirectionClassifier()
        with pytest.raises(NotFittedError):
            clf.predict(_feature_df(3))


def test_uncertainty_high_for_uniform_regime_proba():
    """Uniform distribution across 4 classes → higher entropy than confident prediction."""
    X = _feature_df(1)
    uniform_proba = [[0.25, 0.25, 0.25, 0.25]]
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, uniform_proba)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(1))
        high = clf.uncertainty(X)

    confident_proba = [[0.97, 0.01, 0.01, 0.01]]
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, confident_proba)
        clf2 = OilRegimeClassifier()
        clf2.fit(X, _regime_labels(1))
        low = clf2.uncertainty(X)

    assert high.iloc[0] > low.iloc[0]


def test_uncertainty_returns_series_with_correct_index():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(3))
        result = clf.uncertainty(X)

    assert isinstance(result, pd.Series)
    assert result.name == "uncertainty"
    assert list(result.index) == list(X.index)
    assert (result >= 0).all()


def test_uncertainty_direction_classifier():
    X = _feature_df(3)
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(DIR_CLASSES, DIR_PROBA)
        clf = DirectionClassifier()
        clf.fit(X, pd.Series(["up", "down", "up"]))
        result = clf.uncertainty(X)

    assert isinstance(result, pd.Series)
    assert result.name == "uncertainty"
    assert (result >= 0).all()
