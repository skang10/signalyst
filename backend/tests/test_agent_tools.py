import pytest

from src.agent.registry import ToolRegistry

# ── Registry tests ────────────────────────────────────────────────────────────


def test_tool_decorator_registers_function():
    reg = ToolRegistry()

    @reg.tool({"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]})
    def my_func(x: int, context=None) -> int:
        """Double x."""
        return x * 2

    assert "my_func" in reg._tools


def test_registry_schemas_returns_openai_format():
    reg = ToolRegistry()

    @reg.tool({"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]})
    def add_one(x: int, context=None) -> int:
        """Add one to x."""
        return x + 1

    schemas = reg.schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "add_one"
    assert schema["function"]["description"] == "Add one to x."
    assert schema["function"]["parameters"]["properties"]["x"]["type"] == "integer"


def test_registry_dispatch_calls_function_with_context():
    reg = ToolRegistry()

    class FakeContext:
        value = 0

    @reg.tool({"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]})
    def set_value(n: int, context=None) -> dict:
        """Set context value."""
        context.value = n
        return {"set": n}

    ctx = FakeContext()
    result = reg.dispatch("set_value", {"n": 42}, ctx)
    assert result == {"set": 42}
    assert ctx.value == 42


def test_registry_dispatch_raises_on_unknown_tool():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.dispatch("nonexistent", {}, None)


# ── Tool function tests ───────────────────────────────────────────────────────

from unittest.mock import patch  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.agent.tools import (  # noqa: E402
    AgentContext,
    engineer_features,
    explain_prediction,
    fetch_data,
    run_tabpfn,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def ctx():
    return AgentContext(date_range_start="2024-01-01", date_range_end="2024-12-31")


@pytest.fixture
def ctx_with_signals(ctx):
    dates = pd.date_range("2022-01-01", periods=300, freq="D")
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 90, 300), index=dates, name="CL=F")
    ctx.signals["SPY"] = pd.Series(np.linspace(400, 500, 300), index=dates, name="SPY")
    return ctx


@pytest.fixture
def ctx_with_features(ctx_with_signals):
    dates = pd.date_range("2022-03-01", periods=200, freq="D")
    ctx_with_signals.features = pd.DataFrame(
        np.random.randn(200, 5),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )
    return ctx_with_signals


# ── fetch_data tests ──────────────────────────────────────────────────────────


def test_fetch_data_returns_signal_summary(ctx):
    fake_series = pd.Series(
        [70.0, 71.0, 72.0],
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
        name="CL=F",
    )
    with patch("src.agent.tools.fetch_price_series", return_value=fake_series):
        result = fetch_data(tickers=["CL=F"], fred_series=[], context=ctx)

    assert result["fetched"]["CL=F"] == 3
    assert ctx.signals["CL=F"] is not None


def test_fetch_data_skips_fred_without_api_key(ctx):
    fake_series = pd.Series(
        [70.0],
        index=pd.date_range("2024-01-01", periods=1, freq="D"),
        name="CL=F",
    )
    with (
        patch("src.agent.tools.fetch_price_series", return_value=fake_series),
        patch("src.agent.tools.settings") as mock_settings,
    ):
        mock_settings.fred_api_key = ""
        mock_settings.eia_api_key = ""
        result = fetch_data(tickers=["CL=F"], fred_series=["INDPRO"], context=ctx)

    assert "INDPRO" in result["skipped"]


def test_fetch_data_populates_context_signals(ctx):
    fake_wti = pd.Series(
        [80.0] * 5, index=pd.date_range("2024-01-01", periods=5, freq="D"), name="CL=F"
    )
    fake_spy = pd.Series(
        [450.0] * 5, index=pd.date_range("2024-01-01", periods=5, freq="D"), name="SPY"
    )

    def fake_fetch(ticker, start, end):
        return fake_wti if ticker == "CL=F" else fake_spy

    with patch("src.agent.tools.fetch_price_series", side_effect=fake_fetch):
        fetch_data(tickers=["CL=F", "SPY"], fred_series=[], context=ctx)

    assert "CL=F" in ctx.signals
    assert "SPY" in ctx.signals


# ── engineer_features tests ───────────────────────────────────────────────────


def test_engineer_features_returns_shape(ctx_with_signals):
    result = engineer_features(windows=[5, 20], lags=[1, 5], context=ctx_with_signals)

    assert "shape" in result
    assert result["shape"][1] > 0
    assert ctx_with_signals.features is not None


def test_engineer_features_raises_without_signals(ctx):
    with pytest.raises(ValueError, match="fetch_data"):
        engineer_features(windows=[5], lags=[1], context=ctx)


# ── run_tabpfn tests ──────────────────────────────────────────────────────────


def test_run_tabpfn_regime_returns_summary(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.OilRegimeClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series(["range_bound"] * 40, index=test_idx, name="regime")
        inst.predict_proba.return_value = pd.DataFrame(
            {"range_bound": [0.8] * 40, "bust": [0.2] * 40}, index=test_idx
        )
        inst.uncertainty.return_value = pd.Series([0.5] * 40, index=test_idx, name="uncertainty")

        result = run_tabpfn(task="regime", horizon=20, context=ctx_with_features)

    assert result["task"] == "regime"
    assert "mean_confidence" in result
    assert "mean_entropy" in result
    assert "current_prediction" in result
    assert ctx_with_features.regime_result is not None


def test_run_tabpfn_direction_returns_summary(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.DirectionClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series(["up"] * 40, index=test_idx, name="direction")
        inst.predict_proba.return_value = pd.DataFrame(
            {"up": [0.7] * 40, "down": [0.3] * 40}, index=test_idx
        )
        inst.uncertainty.return_value = pd.Series([0.6] * 40, index=test_idx, name="uncertainty")

        result = run_tabpfn(task="direction", horizon=20, context=ctx_with_features)

    assert result["task"] == "direction"
    assert "mean_confidence" in result
    assert ctx_with_features.direction_result is not None


def test_run_tabpfn_direction_predicts_latest_feature_row(ctx_with_features):
    labeled_idx = ctx_with_features.features.index[:-20]
    latest_idx = ctx_with_features.features.index[-1:]

    with patch("src.agent.tools.DirectionClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.side_effect = [
            pd.Series(["up"] * 40, index=labeled_idx[-40:], name="direction"),
            pd.Series(["down"], index=latest_idx, name="direction"),
        ]
        inst.predict_proba.side_effect = [
            pd.DataFrame({"up": [0.7] * 40, "down": [0.3] * 40}, index=labeled_idx[-40:]),
            pd.DataFrame({"up": [0.2], "down": [0.8]}, index=latest_idx),
        ]
        inst.uncertainty.side_effect = [
            pd.Series([0.6] * 40, index=labeled_idx[-40:], name="uncertainty"),
            pd.Series([0.5], index=latest_idx, name="uncertainty"),
        ]

        result = run_tabpfn(task="direction", horizon=20, context=ctx_with_features)

    latest_predict_frame = inst.predict.call_args_list[-1].args[0]
    assert latest_predict_frame.index.tolist() == latest_idx.tolist()
    assert result["current_prediction"] == "down"
    assert ctx_with_features.direction_result["prediction_date"] == str(latest_idx[0].date())


def test_run_tabpfn_raises_without_features(ctx):
    with pytest.raises(ValueError, match="engineer_features"):
        run_tabpfn(task="regime", horizon=20, context=ctx)


def test_run_tabpfn_raises_without_wti_signal(ctx):
    ctx.features = pd.DataFrame(
        np.random.randn(100, 3),
        index=pd.date_range("2024-01-01", periods=100, freq="D"),
        columns=["f1", "f2", "f3"],
    )
    with pytest.raises(ValueError, match="CL=F"):
        run_tabpfn(task="regime", horizon=20, context=ctx)


# ── explain_prediction tests ──────────────────────────────────────────────────


def test_explain_prediction_returns_structured_dict(ctx):
    result = explain_prediction(
        regime="bust",
        direction="down",
        confidence=0.82,
        key_features=["wti_ret_60", "eia_inventory_slope"],
        context=ctx,
    )

    assert result["regime"] == "bust"
    assert result["direction"] == "down"
    assert result["confidence"] == 0.82
    assert result["key_features"] == ["wti_ret_60", "eia_inventory_slope"]


# ── Smoke test (requires OPENAI_API_KEY) ──────────────────────────────────────

from src.agent.loop import run_agent_loop  # noqa: E402
from src.config import settings as _settings  # noqa: E402


@pytest.mark.integration
@pytest.mark.skipif(
    not _settings.openai_api_key,
    reason="OPENAI_API_KEY not set — skipping live agent loop smoke test",
)
async def test_full_loop_smoke():
    """Runs the real agent loop end-to-end against the OpenAI API."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock

    run_id = uuid.uuid4()
    mock_run = MagicMock()
    mock_run.id = run_id

    with (
        patch("src.agent.loop.AsyncSession") as MockSession,
        patch("src.agent.loop.aioredis.from_url") as mock_redis_factory,
    ):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.get.return_value = mock_run
        MockSession.return_value.__aenter__.return_value = mock_session_ctx

        mock_redis = AsyncMock()
        mock_redis_factory.return_value = mock_redis

        await run_agent_loop(
            run_id,
            "2023-01-01",
            "2023-06-30",
            ["regime_classification", "price_direction"],
        )

    assert mock_run.status is not None
