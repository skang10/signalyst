from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.agent.tools import AgentContext, fetch_data, run_tabpfn

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def ctx():
    return AgentContext(date_range_start="2022-01-01", date_range_end="2022-12-31")


@pytest.fixture
def ctx_with_features(ctx):
    n = 200
    dates = pd.date_range("2022-03-01", periods=n, freq="B")
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 90, n), index=dates, name="CL=F")
    ctx.features = pd.DataFrame(
        np.random.randn(n, 5),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )
    return ctx


# ── AgentContext new fields ────────────────────────────────────────────────────


def test_agent_context_has_new_fields(ctx):
    assert ctx.backtest_result is None
    assert ctx.drift_result is None
    assert ctx.shap_result is None
    assert ctx._regime_clf is None
    assert ctx._regime_X_test is None
    assert ctx._regime_y_test is None
    assert ctx.data_manifest == {}


# ── run_tabpfn stores classifier and test split ────────────────────────────────


def test_run_tabpfn_regime_stores_clf_and_test_split(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.OilRegimeClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series("range_bound", index=test_idx, name="regime")
        inst.predict_proba.return_value = pd.DataFrame({"range_bound": [0.8] * 40}, index=test_idx)
        inst.uncertainty.return_value = pd.Series([0.5] * 40, index=test_idx)

        run_tabpfn(task="regime", context=ctx_with_features)

    assert ctx_with_features._regime_clf is not None
    assert ctx_with_features._regime_X_test is not None
    assert ctx_with_features._regime_y_test is not None


# ── fetch_data writes to data_manifest ────────────────────────────────────────


def test_fetch_data_writes_to_data_manifest(ctx):
    fake_series = pd.Series(
        [70.0] * 5,
        index=pd.date_range("2022-01-01", periods=5, freq="D"),
        name="CL=F",
    )
    with patch("src.agent.tools.fetch_price_series", return_value=fake_series):
        fetch_data(tickers=["CL=F"], fred_series=[], context=ctx)

    assert "data_sources" in ctx.data_manifest
    assert "CL=F" in ctx.data_manifest["data_sources"]
    entry = ctx.data_manifest["data_sources"]["CL=F"]
    assert entry["rows"] == 5
    assert entry["provider"] == "yfinance"


# ── detect_drift ──────────────────────────────────────────────────────────────

from src.agent.tools import detect_drift  # noqa: E402


def test_detect_drift_flags_shifted_distribution(ctx):
    n = 100
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    np.random.seed(0)
    # f1: last 20% shifted by +10 (big shift), f2: random noise (no shift)
    data_f1 = np.concatenate([np.random.randn(80), np.random.randn(20) + 10])
    data_f2 = np.random.randn(n)
    ctx.features = pd.DataFrame({"f1": data_f1, "f2": data_f2}, index=dates)

    result = detect_drift(context=ctx)

    assert result["drift_detected"] is True
    assert "f1" in result["drifted_features"]
    assert ctx.drift_result is not None


def test_detect_drift_result_has_required_keys(ctx):
    n = 100
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    np.random.seed(0)
    ctx.features = pd.DataFrame({"f1": np.random.randn(n), "f2": np.random.randn(n)}, index=dates)

    result = detect_drift(context=ctx)

    assert set(result.keys()) == {"drift_detected", "psi_score", "drifted_features", "ks_results"}
    assert isinstance(result["psi_score"], float)
    assert isinstance(result["ks_results"], dict)


def test_detect_drift_raises_without_features(ctx):
    with pytest.raises(ValueError, match="engineer_features"):
        detect_drift(context=ctx)


# ── evaluate_features ──────────────────────────────────────────────────────────

from unittest.mock import MagicMock  # noqa: E402

from src.agent.tools import evaluate_features  # noqa: E402


def _make_eval_ctx(ctx: AgentContext, n_samples: int = 20, n_features: int = 5):
    dates = pd.date_range("2022-01-01", periods=n_samples, freq="B")
    ctx._regime_clf = MagicMock()
    ctx._regime_X_test = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        index=dates,
        columns=[f"f{i}" for i in range(n_features)],
    )
    ctx._regime_y_test = pd.Series("range_bound", index=dates, name="regime")
    return ctx, dates


def test_evaluate_features_returns_ranked_top_features(ctx):
    ctx, _ = _make_eval_ctx(ctx)
    importance = np.array([0.5, 0.0, 1.0, 0.0, 0.0])

    with patch("src.agent.tools._compute_feature_importance", return_value=importance):
        result = evaluate_features(top_n=3, context=ctx)

    assert len(result["top_features"]) == 3
    assert result["top_features"][0]["name"] == "f2"
    assert result["top_features"][1]["name"] == "f0"
    assert result["n_features_evaluated"] == 5
    assert ctx.shap_result is not None


def test_evaluate_features_returns_all_required_keys(ctx):
    ctx, _ = _make_eval_ctx(ctx)
    importance = np.array([1.0, 0.5, 0.0, 0.0, 0.0])

    with patch("src.agent.tools._compute_feature_importance", return_value=importance):
        result = evaluate_features(top_n=2, context=ctx)

    assert result["top_features"] == [
        {"name": "f0", "importance": 1.0},
        {"name": "f1", "importance": 0.5},
    ]
    assert result["n_features_evaluated"] == 5
    assert result["n_samples_explained"] == 20


def test_evaluate_features_limits_samples_from_latest_rows(ctx):
    ctx, dates = _make_eval_ctx(ctx)
    importance = np.ones(5)

    with patch("src.agent.tools._compute_feature_importance", return_value=importance) as mock_fi:
        evaluate_features(top_n=2, max_samples=3, context=ctx)

    _, X_arg, *_ = mock_fi.call_args.args
    assert X_arg.index.tolist() == dates[-3:].tolist()


def test_evaluate_features_raises_without_regime_clf(ctx):
    with pytest.raises(ValueError, match="run_tabpfn"):
        evaluate_features(context=ctx)


def test_evaluate_features_raises_without_y_test(ctx):
    ctx._regime_clf = MagicMock()
    ctx._regime_X_test = pd.DataFrame([[1.0]], columns=["f0"])
    with pytest.raises(ValueError, match="run_tabpfn"):
        evaluate_features(context=ctx)


# ── fetch_geopolitical_risk ────────────────────────────────────────────────────

from src.agent.tools import fetch_geopolitical_risk  # noqa: E402


def test_fetch_geopolitical_risk_populates_signals(ctx):
    dates = pd.date_range("2022-01-01", periods=10, freq="D")
    fake_gpr = pd.Series(range(10), index=dates, name="GPR", dtype=float)

    with patch("src.agent.tools.fetch_gpr_series", return_value=fake_gpr):
        result = fetch_geopolitical_risk(context=ctx)

    assert "GPR" in ctx.signals
    assert len(ctx.signals["GPR"]) == 10
    assert result["fetched"]["GPR"] == 10


def test_fetch_geopolitical_risk_writes_data_manifest(ctx):
    dates = pd.date_range("2022-01-01", periods=10, freq="D")
    fake_gpr = pd.Series(range(10), index=dates, name="GPR", dtype=float)

    with patch("src.agent.tools.fetch_gpr_series", return_value=fake_gpr):
        fetch_geopolitical_risk(context=ctx)

    entry = ctx.data_manifest["data_sources"]["GPR"]
    assert entry["rows"] == 10
    assert entry["provider"] == "matteoiacoviello.com"
    assert entry["start"] == ctx.date_range_start
    assert entry["end"] == ctx.date_range_end


# ── backtest tool wrapper ──────────────────────────────────────────────────────

from src.agent.tools import backtest  # noqa: E402


def test_backtest_tool_stores_result_in_context(ctx):
    n = 50
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    ctx.features = pd.DataFrame(np.random.randn(n, 3), index=dates, columns=["f1", "f2", "f3"])
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 80, n), index=dates, name="CL=F")
    ctx.signals["SPY"] = pd.Series(np.linspace(400, 450, n), index=dates, name="SPY")

    fake_result = {
        "regime_accuracy": 0.71,
        "strategy_sharpe": 1.43,
        "benchmark_sharpe": 0.89,
        "n_windows": 5,
        "date_range": ["2022-01-01", "2022-03-31"],
    }

    with patch("src.eval.backtest.walk_forward_backtest", return_value=fake_result):
        result = backtest(horizon=20, step=60, max_windows=3, context=ctx)

    assert ctx.backtest_result == fake_result
    assert result == fake_result


def test_backtest_tool_passes_max_windows(ctx):
    n = 50
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    ctx.features = pd.DataFrame(np.random.randn(n, 3), index=dates, columns=["f1", "f2", "f3"])
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 80, n), index=dates, name="CL=F")
    ctx.signals["SPY"] = pd.Series(np.linspace(400, 450, n), index=dates, name="SPY")

    with patch("src.eval.backtest.walk_forward_backtest", return_value={}) as mock_wfb:
        backtest(horizon=20, step=60, max_windows=3, context=ctx)

    assert mock_wfb.call_args.kwargs["max_windows"] == 3


def test_backtest_tool_raises_without_features(ctx):
    with pytest.raises(ValueError, match="engineer_features"):
        backtest(context=ctx)


def test_backtest_tool_raises_without_spy(ctx):
    n = 50
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    ctx.features = pd.DataFrame(np.random.randn(n, 2), index=dates, columns=["f1", "f2"])
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 80, n), index=dates, name="CL=F")

    with pytest.raises(ValueError, match="SPY"):
        backtest(context=ctx)
