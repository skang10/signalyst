# TabPFN Inference Wrappers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap `TabPFNClassifier` into two typed classifiers — `OilRegimeClassifier` (4-class regime detection) and `DirectionClassifier` (binary WTI price direction) — that accept `pd.DataFrame` from `TimeSeriesFeaturizer.transform()` and return labelled `pd.Series`/`pd.DataFrame` with uncertainty scores.

**Architecture:** Both classifiers follow the same pattern: accept a pandas DataFrame, delegate to an internal `TabPFNClassifier`, and return pandas outputs with the input index preserved. `uncertainty()` computes Shannon entropy over the predicted probability distribution. All tests mock `TabPFNClassifier` because v7.1.1 requires a licensed token to download model weights — no real inference in CI.

**Tech Stack:** `tabpfn>=7.1.1`, `pandas`, `numpy`, `scikit-learn` (for `NotFittedError`), `pytest`, `unittest.mock`.

---

## Important: TabPFN requires TABPFN_TOKEN

TabPFN v7.1.1 downloads model weights on first `fit()` and requires a one-time license:
1. Register at https://ux.priorlabs.ai and accept the license
2. Copy your API key from https://ux.priorlabs.ai/account
3. Set `TABPFN_TOKEN=your-key` in `.env`

Without this token, calling `.fit()` raises `TabPFNLicenseError`. The demo script and production code need it; tests do not (they mock TabPFN).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `backend/src/config.py` | Add `tabpfn_token: str = ""` |
| Modify | `.env.example` | Add `TABPFN_TOKEN=` entry |
| Create | `backend/src/inference/classifier.py` | `OilRegimeClassifier` + `DirectionClassifier` |
| Modify | `backend/src/inference/__init__.py` | Re-export both classifiers |
| Create | `backend/tests/test_inference.py` | All classifier tests (mocked TabPFN) |

---

## Task 1: Add TABPFN_TOKEN to Settings and .env.example

**Files:**
- Modify: `backend/src/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add field to Settings**

Open `backend/src/config.py`. Add `tabpfn_token` after `eia_api_key`:

```python
    anthropic_api_key: str = ""
    fred_api_key: str = ""
    eia_api_key: str = ""
    tabpfn_token: str = ""
```

- [ ] **Step 2: Add to .env.example**

Open `.env.example`. Add after `EIA_API_KEY`:

```
EIA_API_KEY=your-eia-api-key
TABPFN_TOKEN=your-tabpfn-token
```

- [ ] **Step 3: Run config tests**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/src/config.py .env.example
git commit -m "feat: add tabpfn_token to Settings and .env.example"
```

---

## Task 2: OilRegimeClassifier — fit, predict, predict_proba

**Files:**
- Create: `backend/src/inference/classifier.py`
- Create: `backend/tests/test_inference.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_inference.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import NotFittedError

from src.inference.classifier import OilRegimeClassifier


def _feature_df(n: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        rng.standard_normal((n, 5)),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )


def _regime_labels(n: int = 10) -> pd.Series:
    labels = (["bull_supercycle"] * 3 + ["range_bound"] * 3 +
              ["bust"] * 2 + ["geopolitical_spike"] * 2)[:n]
    return pd.Series(labels, name="regime")


def _mock_clf(classes: list[str], proba: list[list[float]]) -> MagicMock:
    mock = MagicMock()
    mock.classes_ = np.array(classes)
    mock.predict_proba.return_value = np.array(proba)
    mock.predict.return_value = np.array(
        [classes[int(np.argmax(row))] for row in proba]
    )
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
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_inference.py -v
```

Expected: `ImportError` — `classifier.py` doesn't exist.

- [ ] **Step 3: Create classifier.py with OilRegimeClassifier**

Create `backend/src/inference/classifier.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.exceptions import NotFittedError
from tabpfn import TabPFNClassifier


class OilRegimeClassifier:
    """TabPFN-backed 4-class oil market regime classifier.

    Regimes: bull_supercycle | range_bound | bust | geopolitical_spike

    Args:
        n_estimators: number of TabPFN ensemble members (more = slower but smoother proba)

    Example:
        >>> clf = OilRegimeClassifier()
        >>> clf.fit(X_train, y_train)
        >>> clf.predict(X_test)
        date
        2024-01-01    geopolitical_spike
        dtype: object
    """

    def __init__(self, n_estimators: int = 8) -> None:
        self._clf = TabPFNClassifier(n_estimators=n_estimators)
        self._fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> OilRegimeClassifier:
        """Fit on feature matrix X and regime label series y."""
        self._clf.fit(X.to_numpy(), y.to_numpy())
        self._fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> pd.Series:
        """Return predicted regime label for each row in X."""
        self._check_fitted()
        labels = self._clf.predict(X.to_numpy())
        return pd.Series(labels, index=X.index, name="regime")

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return class probabilities for each row in X.

        Returns:
            DataFrame with columns = regime names, index = X.index.
        """
        self._check_fitted()
        proba = self._clf.predict_proba(X.to_numpy())
        return pd.DataFrame(proba, index=X.index, columns=self._clf.classes_)

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise NotFittedError("Call fit() before predict().")
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_inference.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/inference/classifier.py backend/tests/test_inference.py
git commit -m "feat: add OilRegimeClassifier with fit/predict/predict_proba"
```

---

## Task 3: DirectionClassifier — fit, predict, predict_proba

**Files:**
- Modify: `backend/src/inference/classifier.py`
- Modify: `backend/tests/test_inference.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_inference.py`:

```python
from src.inference.classifier import DirectionClassifier

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
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_inference.py::test_direction_predict_returns_series_with_correct_index -v
```

Expected: `ImportError` — `DirectionClassifier` not defined.

- [ ] **Step 3: Add DirectionClassifier to classifier.py**

Append to `backend/src/inference/classifier.py`:

```python
class DirectionClassifier:
    """TabPFN-backed binary classifier for WTI price direction (up/down next 4 weeks).

    Args:
        n_estimators: number of TabPFN ensemble members

    Example:
        >>> clf = DirectionClassifier()
        >>> clf.fit(X_train, y_train)  # y_train: pd.Series of "up"/"down"
        >>> clf.predict(X_test)
        date
        2024-01-01    up
        dtype: object
    """

    def __init__(self, n_estimators: int = 8) -> None:
        self._clf = TabPFNClassifier(n_estimators=n_estimators)
        self._fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> DirectionClassifier:
        """Fit on feature matrix X and direction labels y ('up' or 'down')."""
        self._clf.fit(X.to_numpy(), y.to_numpy())
        self._fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> pd.Series:
        """Return predicted direction ('up' or 'down') for each row in X."""
        self._check_fitted()
        labels = self._clf.predict(X.to_numpy())
        return pd.Series(labels, index=X.index, name="direction")

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return class probabilities for each row in X.

        Returns:
            DataFrame with columns ['down', 'up'], index = X.index.
        """
        self._check_fitted()
        proba = self._clf.predict_proba(X.to_numpy())
        return pd.DataFrame(proba, index=X.index, columns=self._clf.classes_)

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise NotFittedError("Call fit() before predict().")
```

- [ ] **Step 4: Run all inference tests**

```bash
cd backend && uv run pytest tests/test_inference.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/inference/classifier.py backend/tests/test_inference.py
git commit -m "feat: add DirectionClassifier with fit/predict/predict_proba"
```

---

## Task 4: uncertainty() — Shannon entropy for both classifiers

**Files:**
- Modify: `backend/src/inference/classifier.py`
- Modify: `backend/tests/test_inference.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_inference.py`:

```python
def test_uncertainty_high_for_uniform_regime_proba():
    """Uniform distribution across 4 classes → max entropy."""
    X = _feature_df(1)
    uniform_proba = [[0.25, 0.25, 0.25, 0.25]]
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, uniform_proba)
        clf = OilRegimeClassifier()
        clf.fit(X, _regime_labels(1))
        result = clf.uncertainty(X)

    confident_proba = [[0.97, 0.01, 0.01, 0.01]]
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, confident_proba)
        clf2 = OilRegimeClassifier()
        clf2.fit(X, _regime_labels(1))
        low = clf2.uncertainty(X)

    assert result.iloc[0] > low.iloc[0]


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
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_inference.py::test_uncertainty_returns_series_with_correct_index -v
```

Expected: `AttributeError` — `uncertainty` not defined.

- [ ] **Step 3: Add uncertainty() to both classifiers**

In `OilRegimeClassifier`, add after `predict_proba()` and before `_check_fitted()`:

```python
    def uncertainty(self, X: pd.DataFrame) -> pd.Series:
        """Return Shannon entropy of predicted distribution (higher = less certain).

        Returns:
            Series with index = X.index, name = "uncertainty", values >= 0.
        """
        proba = self.predict_proba(X).to_numpy()
        proba = np.clip(proba, 1e-10, 1.0)
        entropy = -np.sum(proba * np.log(proba), axis=1)
        return pd.Series(entropy, index=X.index, name="uncertainty")
```

In `DirectionClassifier`, add the identical method after `predict_proba()` and before `_check_fitted()`:

```python
    def uncertainty(self, X: pd.DataFrame) -> pd.Series:
        """Return Shannon entropy of predicted distribution (higher = less certain).

        Returns:
            Series with index = X.index, name = "uncertainty", values >= 0.
        """
        proba = self.predict_proba(X).to_numpy()
        proba = np.clip(proba, 1e-10, 1.0)
        entropy = -np.sum(proba * np.log(proba), axis=1)
        return pd.Series(entropy, index=X.index, name="uncertainty")
```

- [ ] **Step 4: Run all inference tests**

```bash
cd backend && uv run pytest tests/test_inference.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/inference/classifier.py backend/tests/test_inference.py
git commit -m "feat: add uncertainty() via Shannon entropy to both classifiers"
```

---

## Task 5: Wire up __init__.py + full test suite

**Files:**
- Modify: `backend/src/inference/__init__.py`

- [ ] **Step 1: Export public API**

Replace `backend/src/inference/__init__.py` contents:

```python
from src.inference.classifier import DirectionClassifier, OilRegimeClassifier

__all__ = ["DirectionClassifier", "OilRegimeClassifier"]
```

- [ ] **Step 2: Verify import**

```bash
cd backend && uv run python -c "from src.inference import OilRegimeClassifier, DirectionClassifier; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass (36 existing + 13 new = 49 total).

- [ ] **Step 4: Run linter and type checker**

```bash
cd backend && uv run ruff check src/inference/ tests/test_inference.py && uv run mypy src/inference/
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/inference/__init__.py
git commit -m "feat: export inference classifiers from src.inference"
```

---

## Next Sessions

| Session | Focus |
|---|---|
| Session 3 | `src/db/` — SQLModel run/history models + Alembic migration |
| Session 4 | `src/agent/` — tool definitions + ReAct loop using Anthropic SDK |
| Session 5 | Wire up API routes (replace 501s) + WebSocket Redis pub/sub |
| Session 6 | Frontend — RegimeDashboard + AgentStream components |
