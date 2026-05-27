from __future__ import annotations

from typing import Any

import pandas as pd

from src.agent.tools import _make_direction_labels, _make_regime_labels
from src.inference import DirectionClassifier, OilRegimeClassifier


def _annualised_sharpe(returns: list[float]) -> float:
    s = pd.Series(returns).dropna()
    if s.std() == 0:
        return 0.0
    return float((s.mean() / s.std()) * (252**0.5))


def walk_forward_backtest(
    features: pd.DataFrame,
    wti: pd.Series,
    spy: pd.Series,
    horizon: int = 20,
    step: int = 20,
    min_train: int = 120,
    max_windows: int | None = None,
) -> dict[str, Any]:
    """Walk-forward evaluation using an expanding window.

    Returns regime accuracy, strategy Sharpe (long WTI on 'up' signal, flat otherwise),
    benchmark Sharpe (buy-and-hold SPY), window count, and date range.
    """
    regime_labels = _make_regime_labels(wti, features.index)
    direction_labels = _make_direction_labels(wti, features.index, horizon=horizon)

    regime_correct = 0
    regime_total = 0
    strategy_returns: list[float] = []
    spy_returns: list[float] = []
    n_windows = 0

    windows = list(range(min_train, len(features) - horizon, step))
    if max_windows is not None:
        windows = windows[-max_windows:] if max_windows > 0 else []

    for t in windows:
        X_train = features.iloc[:t]
        X_test = features.iloc[t : t + horizon]
        y_regime_train = regime_labels.iloc[:t]
        y_regime_test = regime_labels.iloc[t : t + horizon]
        # A direction label at row i uses WTI[i + horizon]; keep training labels
        # whose outcomes resolve before the first test row.
        y_dir_train = direction_labels.reindex(features.iloc[: max(0, t - horizon)].index).dropna()
        y_dir_test = direction_labels.reindex(X_test.index).dropna()

        # Regime accuracy
        clf = OilRegimeClassifier(n_estimators=8)
        clf.fit(X_train, y_regime_train)
        preds = clf.predict(X_test)
        regime_correct += int((preds == y_regime_test).sum())
        regime_total += len(y_regime_test)

        # Direction strategy returns
        if len(y_dir_train) > 0 and len(y_dir_test) > 0:
            dir_clf = DirectionClassifier(n_estimators=8)
            dir_clf.fit(X_train.loc[y_dir_train.index], y_dir_train)
            pred_dir = dir_clf.predict(X_test.loc[y_dir_test.index])
            wti_ret = (wti.shift(-horizon) / wti - 1).reindex(y_dir_test.index)
            strategy_returns.extend(wti_ret.where(pred_dir == "up", 0).tolist())
            spy_ret = (spy.shift(-horizon) / spy - 1).reindex(y_dir_test.index)
            spy_returns.extend(spy_ret.tolist())

        n_windows += 1

    regime_accuracy = regime_correct / regime_total if regime_total > 0 else 0.0

    return {
        "regime_accuracy": round(regime_accuracy, 4),
        "strategy_sharpe": _annualised_sharpe(strategy_returns),
        "benchmark_sharpe": _annualised_sharpe(spy_returns),
        "n_windows": n_windows,
        "date_range": [str(features.index[0].date()), str(features.index[-1].date())],
    }
