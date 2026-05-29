from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.agent.registry import registry
from src.data import connector_registry
from src.featurizer import TimeSeriesFeaturizer
from src.inference import DirectionClassifier, OilRegimeClassifier

# Hand-labeled historical regime periods (same as demo.py — source of truth).
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),
    ("2020-02-01", "2020-10-31", "bust"),
    ("2021-01-01", "2022-06-30", "bull_supercycle"),
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),
]


@dataclass
class AgentContext:
    date_range_start: str
    date_range_end: str
    signals: dict[str, pd.Series] = field(default_factory=dict)
    features: pd.DataFrame | None = None
    regime_result: dict[str, Any] | None = None
    direction_result: dict[str, Any] | None = None
    backtest_result: dict[str, Any] | None = None
    drift_result: dict[str, Any] | None = None
    shap_result: dict[str, Any] | None = None
    _regime_clf: Any | None = None
    _regime_X_test: pd.DataFrame | None = None
    _regime_y_test: pd.Series | None = None
    data_manifest: dict[str, Any] = field(default_factory=dict)


def _make_regime_labels(wti: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    ret5 = wti_daily.pct_change(5)
    ret60 = wti_daily.pct_change(60)
    labels = pd.Series("range_bound", index=index, name="regime")
    labels[ret60 > 0.15] = "bull_supercycle"
    labels[ret60 < -0.15] = "bust"
    labels[ret5 > 0.08] = "geopolitical_spike"
    for start, end, regime in _KNOWN_REGIMES:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime
    return labels


def _make_direction_labels(wti: pd.Series, index: pd.DatetimeIndex, horizon: int = 20) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    forward_ret = wti_daily.shift(-horizon) / wti_daily - 1
    forward_ret = forward_ret.dropna()
    labels = forward_ret.map(lambda r: "up" if r > 0 else "down")
    labels.name = "direction"
    return labels


@registry.tool(
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    }
)
def list_data_sources(context: AgentContext | None = None) -> dict[str, Any]:
    """List all available data connectors and which ones are blocked due to missing config."""
    return connector_registry.list()


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "source_name": {
                "type": "string",
                "description": "Connector name as returned by list_data_sources",
            },
            "params": {
                "type": "object",
                "description": "Connector-specific params — see params_schema in list_data_sources",
            },
        },
        "required": ["source_name", "params"],
    }
)
def fetch_from_source(
    source_name: str,
    params: dict[str, Any],
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Fetch data from a named connector into the analysis context.

    Returns a fetch summary dict, or an error dict if the source is unknown or blocked.
    """
    if source_name not in connector_registry._connectors:
        return {"error": "unknown_source", "detail": f"No connector named {source_name!r}"}
    if not connector_registry.is_available(source_name):
        meta = connector_registry._connectors[source_name]
        return {
            "error": "blocked",
            "reason": f"{meta.requires_env} not set",
        }
    try:
        return connector_registry.fetch(source_name, params, context)
    except Exception as exc:
        return {"error": "fetch_failed", "detail": str(exc)}


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "windows": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Rolling window sizes in days, e.g. [5, 20, 60]",
            },
            "lags": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Lag periods in days, e.g. [1, 5, 20]",
            },
        },
        "required": ["windows", "lags"],
    }
)
def engineer_features(windows: list[int], lags: list[int], context: AgentContext) -> dict[str, Any]:
    """Featurize the fetched signals into a tabular feature matrix."""
    if not context.signals:
        raise ValueError("No signals in context. Call fetch_from_source first.")
    featurizer = TimeSeriesFeaturizer(windows=windows, lags=lags)
    features = featurizer.transform(context.signals)
    context.features = features
    start = str(features.index[0].date())
    end = str(features.index[-1].date())
    return {"shape": list(features.shape), "date_range": [start, end]}


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "enum": ["regime", "direction"],
                "description": "'regime' for OilRegimeClassifier, 'direction' for DirectionClassifier",  # noqa: E501
            },
            "horizon": {
                "type": "integer",
                "description": "Forward-return horizon in trading days for direction labels (ignored for regime)",  # noqa: E501
                "default": 20,
            },
        },
        "required": ["task"],
    }
)
def run_tabpfn(task: str, horizon: int = 20, context: AgentContext | None = None) -> dict[str, Any]:
    """Run TabPFN classification for regime or price direction."""
    if context is None or context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")
    if "CL=F" not in context.signals:
        raise ValueError(
            "WTI price series ('CL=F') not found in context.signals. "
            "Call fetch_from_source with source_name='yfinance'."
        )

    features = context.features.dropna()
    wti = context.signals["CL=F"]

    if task == "regime":
        labels = _make_regime_labels(wti, features.index)
        split = int(len(features) * 0.8)
        X_train, X_test = features.iloc[:split], features.iloc[split:]
        y_train = labels.iloc[:split]
        regime_clf = OilRegimeClassifier(n_estimators=8)
        regime_clf.fit(X_train, y_train)
        context._regime_clf = regime_clf
        context._regime_X_test = X_test
        context._regime_y_test = labels.iloc[split:]
        pred = regime_clf.predict(X_test)
        proba = regime_clf.predict_proba(X_test)
        uncertainty = regime_clf.uncertainty(X_test)
        mean_conf = float(proba.max(axis=1).mean())
        mean_entropy = float(uncertainty.mean())
        current = str(pred.iloc[-1])
        distribution = pred.value_counts().to_dict()
        context.regime_result = {
            "regime": current,
            "confidence": mean_conf,
            "entropy": mean_entropy,
            "distribution": {str(k): int(v) for k, v in distribution.items()},
        }
        return {
            "task": "regime",
            "current_prediction": current,
            "mean_confidence": mean_conf,
            "mean_entropy": mean_entropy,
            "test_size": len(X_test),
            "label_distribution": {str(k): int(v) for k, v in distribution.items()},
        }

    # direction
    direction_labels = _make_direction_labels(wti, features.index, horizon=horizon)
    common_idx = features.index.intersection(direction_labels.index)
    features_dir = features.loc[common_idx]
    labels_dir = direction_labels.loc[common_idx]
    split = int(len(features_dir) * 0.8)
    X_train, X_test = features_dir.iloc[:split], features_dir.iloc[split:]
    y_train = labels_dir.iloc[:split]
    dir_clf = DirectionClassifier(n_estimators=8)
    dir_clf.fit(X_train, y_train)
    pred = dir_clf.predict(X_test)
    proba = dir_clf.predict_proba(X_test)
    uncertainty = dir_clf.uncertainty(X_test)
    test_mean_conf = float(proba.max(axis=1).mean())
    mean_entropy = float(uncertainty.mean())
    latest_features = features.iloc[[-1]]
    current_pred = dir_clf.predict(latest_features)
    current_proba = dir_clf.predict_proba(latest_features)
    current_uncertainty = dir_clf.uncertainty(latest_features)
    current = str(current_pred.iloc[-1])
    current_conf = float(current_proba.max(axis=1).iloc[-1])
    current_entropy = float(current_uncertainty.iloc[-1])
    prediction_date = str(latest_features.index[-1].date())
    distribution = pred.value_counts().to_dict()
    context.direction_result = {
        "direction": current,
        "confidence": current_conf,
        "entropy": current_entropy,
        "prediction_date": prediction_date,
        "distribution": {str(k): int(v) for k, v in distribution.items()},
    }
    return {
        "task": "direction",
        "current_prediction": current,
        "prediction_date": prediction_date,
        "mean_confidence": current_conf,
        "test_mean_confidence": test_mean_conf,
        "mean_entropy": mean_entropy,
        "test_size": len(X_test),
        "label_distribution": {str(k): int(v) for k, v in distribution.items()},
    }


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "regime": {"type": "string", "description": "Predicted regime label"},
            "direction": {
                "type": "string",
                "description": "Predicted price direction ('up' or 'down')",
            },
            "confidence": {"type": "number", "description": "Mean confidence score 0-1"},
            "key_features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Feature names most relevant to this prediction",
            },
        },
        "required": ["regime", "direction", "confidence", "key_features"],
    }
)
def explain_prediction(
    regime: str,
    direction: str,
    confidence: float,
    key_features: list[str],
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Assemble prediction inputs for the agent's final narrative explanation."""
    return {
        "regime": regime,
        "direction": direction,
        "confidence": confidence,
        "key_features": key_features,
    }


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    expected_dist = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_dist = np.histogram(actual, bins=breakpoints)[0] / len(actual)
    expected_dist = np.clip(expected_dist, 1e-4, None)
    actual_dist = np.clip(actual_dist, 1e-4, None)
    return float(np.sum((actual_dist - expected_dist) * np.log(actual_dist / expected_dist)))


@registry.tool(
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    }
)
def detect_drift(context: AgentContext) -> dict[str, Any]:
    """Detect feature distribution drift using KS test and PSI on historical vs recent data."""
    if context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")

    from scipy.stats import ks_2samp

    features = context.features.dropna()
    split = int(len(features) * 0.8)
    historical = features.iloc[:split]
    recent = features.iloc[split:]

    ks_results: dict[str, Any] = {}
    drifted: list[str] = []
    for col in features.columns:
        stat, pval = ks_2samp(historical[col].values, recent[col].values)
        ks_results[col] = {"statistic": round(float(stat), 4), "p_value": round(float(pval), 4)}
        if pval < 0.05:
            drifted.append(col)

    psi_score = float(
        np.mean([_psi(historical[col].values, recent[col].values) for col in features.columns])
    )

    context.drift_result = {
        "drift_detected": psi_score >= 0.1,
        "psi_score": round(psi_score, 4),
        "drifted_features": drifted,
        "ks_results": ks_results,
    }
    return context.drift_result


def _compute_feature_importance(
    clf: OilRegimeClassifier, X: pd.DataFrame, y: pd.Series, n_repeats: int = 0
) -> np.ndarray:
    if n_repeats == 0:
        # Spearman correlation — zero additional TabPFN API calls
        y_codes = y.astype("category").cat.codes
        return np.asarray(
            np.nan_to_num(
                [abs(float(X[col].corr(y_codes, method="spearman"))) for col in X.columns]
            )
        )

    # Permutation importance — (n_repeats × n_features + 1) TabPFN API calls
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import accuracy_score

    feature_names = list(X.columns)

    def _score(estimator: OilRegimeClassifier, X_arr: np.ndarray, y_arr: np.ndarray) -> float:
        return float(
            accuracy_score(y_arr, estimator.predict(pd.DataFrame(X_arr, columns=feature_names)))
        )

    result = permutation_importance(
        clf,
        X.to_numpy(),
        y.to_numpy(),
        scoring=_score,
        n_repeats=n_repeats,
        random_state=42,
    )
    return np.asarray(result.importances_mean)


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "Number of top features to return by importance. Default 10.",
                "default": 10,
            },
            "max_samples": {
                "type": "integer",
                "description": "Maximum latest test rows to evaluate. Default 50.",
                "default": 50,
            },
            "n_repeats": {
                "type": "integer",
                "description": (
                    "0=Spearman correlation (no extra API calls, quick mode default); "
                    "1+=permutation importance (n_repeats×n_features+1 API calls, full mode)."
                ),
                "default": 0,
            },
        },
        "required": [],
    }
)
def evaluate_features(
    top_n: int = 10,
    max_samples: int = 50,
    n_repeats: int = 0,
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Rank features by Spearman correlation (quick, n_repeats=0) or permutation importance."""
    if (
        context is None
        or context._regime_clf is None
        or context._regime_X_test is None
        or context._regime_y_test is None
    ):
        raise ValueError(
            "No fitted regime classifier in context. Call run_tabpfn(task='regime') first."
        )

    X_explain = (
        context._regime_X_test.tail(max_samples) if max_samples > 0 else context._regime_X_test
    )
    y_explain = context._regime_y_test.loc[X_explain.index]

    importance = _compute_feature_importance(context._regime_clf, X_explain, y_explain, n_repeats)

    feature_names = list(X_explain.columns)
    ranked = sorted(zip(feature_names, importance.tolist()), key=lambda x: x[1], reverse=True)

    top = [{"name": name, "importance": round(float(imp), 4)} for name, imp in ranked[:top_n]]

    context.shap_result = {
        "top_features": top,
        "n_features_evaluated": len(feature_names),
        "n_samples_explained": len(X_explain),
    }
    return context.shap_result


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "horizon": {
                "type": "integer",
                "description": "Forward-return horizon in trading days. Default 20.",
                "default": 20,
            },
            "step": {
                "type": "integer",
                "description": "Walk-forward step size in days. Default 20.",
                "default": 20,
            },
            "max_windows": {
                "type": ["integer", "null"],
                "description": "Maximum number of most recent walk-forward windows. Omit for all.",
            },
        },
        "required": [],
    }
)
def backtest(
    horizon: int = 20,
    step: int = 20,
    max_windows: int | None = None,
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Walk-forward backtest: regime accuracy + direction strategy Sharpe vs SPY buy-and-hold."""
    if context is None or context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")
    if "CL=F" not in context.signals:
        raise ValueError("WTI signal ('CL=F') not found. Call fetch_from_source first.")
    if "SPY" not in context.signals:
        raise ValueError(
            "SPY signal not found. "
            "Call fetch_from_source with source_name='yfinance' and include 'SPY' in tickers."
        )

    from src.eval.backtest import walk_forward_backtest as _wfb

    result = _wfb(
        features=context.features.dropna(),
        wti=context.signals["CL=F"],
        spy=context.signals["SPY"],
        horizon=horizon,
        step=step,
        max_windows=max_windows,
    )
    context.backtest_result = result
    return result
