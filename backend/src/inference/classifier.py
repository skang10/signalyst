from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import tabpfn_client
from sklearn.exceptions import NotFittedError
from tabpfn_client import TabPFNClassifier

from src.config import settings


class OilRegimeClassifier:
    """TabPFN-backed 4-class oil market regime classifier.

    Regimes: bull_supercycle | range_bound | bust | geopolitical_spike

    Args:
        n_estimators: number of TabPFN ensemble members (more = smoother probabilities)

    Note:
        Requires TABPFN_TOKEN env var set for API authentication.
        Register and accept license at https://ux.priorlabs.ai

    Example:
        >>> clf = OilRegimeClassifier()
        >>> clf.fit(X_train, y_train)  # y_train: pd.Series of regime label strings
        >>> clf.predict(X_test)
        date
        2024-01-01    geopolitical_spike
        Name: regime, dtype: object
    """

    def __init__(self, n_estimators: int = 8) -> None:
        if settings.tabpfn_token:
            tabpfn_client.set_access_token(settings.tabpfn_token)
        self._clf = TabPFNClassifier(n_estimators=n_estimators)
        self._fitted = False

    @property
    def estimators_(self) -> list[Any]:
        """Return the ensemble members for SHAP interpretability."""
        return self._clf.estimators_  # type: ignore[no-any-return]

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

    def uncertainty(self, X: pd.DataFrame) -> pd.Series:
        """Return Shannon entropy of predicted distribution (higher = less certain).

        Returns:
            Series with index = X.index, name = "uncertainty", values >= 0.
        """
        proba = self.predict_proba(X).to_numpy()
        proba = np.clip(proba, 1e-10, 1.0)
        entropy = -np.sum(proba * np.log(proba), axis=1)
        return pd.Series(entropy, index=X.index, name="uncertainty")

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise NotFittedError("Call fit() before predict().")


class DirectionClassifier:
    """TabPFN-backed binary classifier for WTI price direction (up/down next 4 weeks).

    Args:
        n_estimators: number of TabPFN ensemble members

    Note:
        Requires TABPFN_TOKEN env var set for API authentication.

    Example:
        >>> clf = DirectionClassifier()
        >>> clf.fit(X_train, y_train)  # y_train: pd.Series of "up" / "down"
        >>> clf.predict(X_test)
        date
        2024-01-01    up
        Name: direction, dtype: object
    """

    def __init__(self, n_estimators: int = 8) -> None:
        if settings.tabpfn_token:
            tabpfn_client.set_access_token(settings.tabpfn_token)
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

    def uncertainty(self, X: pd.DataFrame) -> pd.Series:
        """Return Shannon entropy of predicted distribution (higher = less certain).

        Returns:
            Series with index = X.index, name = "uncertainty", values >= 0.
        """
        proba = self.predict_proba(X).to_numpy()
        proba = np.clip(proba, 1e-10, 1.0)
        entropy = -np.sum(proba * np.log(proba), axis=1)
        return pd.Series(entropy, index=X.index, name="uncertainty")

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise NotFittedError("Call fit() before predict().")
