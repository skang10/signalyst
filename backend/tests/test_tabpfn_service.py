from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import src.db.models  # noqa: F401 — registers all tables
from src.db.models import (
    AnalysisResult,
    DataArtifact,
    FeatureArtifact,
    MarketProfile,
    SessionStage,
    SessionStatus,
)
from src.db.models import Session as SessionModel
from src.services.hashing import canonical_json, stable_hash
from src.services.tabpfn import run_tabpfn_service


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append(json.loads(message))

    async def aclose(self) -> None:
        pass


async def _make_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation() -> None:
    """`_run`'s within-session cache-hit branch must stop at EXPLAINING (not FOLLOW_UP)
    and hand off to run_explanation_service — this is the fix for the stale
    'PR 2: skip EXPLAINING' shortcut."""
    engine = await _make_engine()
    session_id = uuid.uuid4()
    da_id = uuid.uuid4()
    fa_id = uuid.uuid4()
    ar_id = uuid.uuid4()

    # _run computes feature_hash as stable_hash(matrix_hash, canonical_json(regime_labels),
    # canonical_json(analysis_config)) with these exact constants — replicate it so our
    # pre-seeded AnalysisResult is recognized as a within-session cache hit.
    feature_hash = stable_hash(
        "matrix-hash",
        canonical_json(["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]),
        canonical_json({}),
    )

    async with AsyncSession(engine) as db:
        db.add(
            SessionModel(
                id=session_id,
                market_profile="oil",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
                stage=SessionStage.ANALYZING.value,
                status=SessionStatus.RUNNING.value,
            )
        )
        db.add(
            DataArtifact(
                id=da_id,
                session_id=session_id,
                data_manifest={"tickers": ["CL=F"]},
                source_hash="src-hash",
            )
        )
        db.add(
            FeatureArtifact(
                id=fa_id,
                session_id=session_id,
                data_artifact_id=da_id,
                matrix_hash="matrix-hash",
            )
        )
        db.add(
            AnalysisResult(
                id=ar_id,
                session_id=session_id,
                feature_artifact_id=fa_id,
                regime={"regime": "bull_supercycle"},
                feature_hash=feature_hash,
            )
        )
        db.add(
            MarketProfile(
                id="oil",
                name="Oil Markets",
                default_connectors=["yfinance", "fred", "eia", "gpr"],
                default_connector_params={
                    "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
                    "fred": {"series_ids": ["INDPRO"]},
                },
                default_featurizer_config={},
                regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
                regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08},
                primary_ticker="CL=F",
            )
        )
        await db.commit()

    fake_redis = _FakeRedis()
    with (
        patch("src.services.tabpfn.aioredis.Redis.from_url", return_value=fake_redis),
        patch(
            "src.services.tabpfn.run_explanation_service", new_callable=AsyncMock
        ) as mock_explain,
    ):
        await run_tabpfn_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.stage == SessionStage.EXPLAINING.value
    assert s.status == SessionStatus.RUNNING.value
    mock_explain.assert_awaited_once_with(session_id, engine)
    assert any(
        m["type"] == "stage_transition" and m["to"] == "explaining" for m in fake_redis.published
    )


@pytest.mark.asyncio
async def test_tabpfn_run_persists_feature_importance(tmp_path) -> None:
    engine = await _make_engine()
    session_id = uuid.uuid4()
    da_id = uuid.uuid4()
    fa_id = uuid.uuid4()

    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    features = pd.DataFrame(
        {
            "CL=F_close": np.linspace(70.0, 90.0, n),
            "f1": np.linspace(1.0, 2.0, n),
            "f2": np.sin(np.linspace(0, 10, n)),
        },
        index=dates,
    )
    matrix_path = tmp_path / "features.parquet"
    features.to_parquet(matrix_path)

    fixed_labels = pd.Series(["range_bound", "trend_up"] * (n // 2), index=dates, name="regime")

    async with AsyncSession(engine) as db:
        db.add(
            SessionModel(
                id=session_id,
                market_profile="oil",
                timeframe_start=date(2024, 1, 1),
                timeframe_end=date(2024, 6, 1),
                stage=SessionStage.ANALYZING.value,
                status=SessionStatus.RUNNING.value,
            )
        )
        db.add(
            DataArtifact(
                id=da_id,
                session_id=session_id,
                data_manifest={"tickers": ["CL=F"]},
                source_hash="src-hash",
            )
        )
        db.add(
            FeatureArtifact(
                id=fa_id,
                session_id=session_id,
                data_artifact_id=da_id,
                matrix_hash="matrix-hash-2",
                feature_matrix_ref=str(matrix_path),
            )
        )
        db.add(
            MarketProfile(
                id="oil",
                name="Oil Markets",
                default_connectors=["yfinance", "fred", "eia", "gpr"],
                default_connector_params={
                    "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
                    "fred": {"series_ids": ["INDPRO"]},
                },
                default_featurizer_config={},
                regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
                regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08},
                primary_ticker="CL=F",
            )
        )
        await db.commit()

    fake_redis = _FakeRedis()
    with (
        patch("src.services.tabpfn.aioredis.Redis.from_url", return_value=fake_redis),
        patch("src.services.tabpfn.settings.tabpfn_token", "fake-token"),
        patch("src.services.tabpfn._make_regime_labels", return_value=fixed_labels),
        patch("src.inference.OilRegimeClassifier") as MockRegimeCls,
        patch("src.inference.DirectionClassifier") as MockDirCls,
        patch("src.services.tabpfn.run_explanation_service", new_callable=AsyncMock),
    ):
        # predict()/predict_proba() return fixed values regardless of call args, so the
        # index/length of these mocks doesn't need to match the real train/test split —
        # downstream code only does value_counts().idxmax() and column .mean() on them.
        regime_inst = MockRegimeCls.return_value
        regime_inst.predict.return_value = pd.Series(["range_bound"] * 5, name="regime")
        regime_inst.predict_proba.return_value = pd.DataFrame({"range_bound": [0.8] * 5})

        dir_inst = MockDirCls.return_value
        dir_inst.predict.return_value = pd.Series(["up"] * 5, name="direction")
        dir_inst.predict_proba.return_value = pd.DataFrame({"up": [0.6] * 5})

        await run_tabpfn_service(session_id, engine)

    async with AsyncSession(engine) as db:
        ar = (
            (
                await db.execute(
                    select(AnalysisResult).where(AnalysisResult.session_id == session_id)
                )
            )
            .scalars()
            .first()
        )

    assert ar is not None
    assert ar.feature_importance is not None
    assert set(ar.feature_importance.keys()) == {
        "top_features",
        "n_features_evaluated",
        "n_samples_explained",
    }
    assert ar.feature_importance["n_features_evaluated"] == 3
    assert len(ar.feature_importance["top_features"]) <= 10


def test_feature_importance_ranks_by_correlation_and_caps_samples() -> None:
    from src.services.tabpfn import _feature_importance

    n = 20
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    y = pd.Series(["a", "b"] * (n // 2), index=dates, name="regime")
    X = pd.DataFrame(
        {
            "f_corr": [0, 1] * (n // 2),  # perfectly tracks y
            "f_other": np.sin(np.linspace(0, 10, n)),  # unrelated pattern
        },
        index=dates,
    )

    result = _feature_importance(clf=None, X_test=X, y_test=y, max_samples=10, top_n=2)

    assert result["top_features"][0]["name"] == "f_corr"
    assert result["top_features"][0]["importance"] == 1.0
    assert len(result["top_features"]) == 2
    assert result["n_features_evaluated"] == 2
    assert result["n_samples_explained"] == 10


def test_make_regime_labels_generic_thresholds_and_symmetric_spike() -> None:
    from src.services.tabpfn import _make_regime_labels

    index = pd.date_range("2024-01-01", periods=70, freq="D")
    # Flat at 100 for 65 days, then a sharp 10% drop that holds for 5 days.
    prices = [100.0] * 65 + [90.0] * 5
    proxy = pd.Series(prices, index=index)

    regime_labels = ["trend_up", "range_bound", "trend_down", "spike"]
    thresholds = {"trend_up": 0.15, "trend_down": -0.15, "spike": 0.05}

    labels = _make_regime_labels(proxy, index, regime_labels, thresholds, known_regimes=[])

    # Day 66 (iloc 65): 5-day return = (90-100)/100 = -0.10, abs(-0.10) > 0.05 -> spike
    assert labels.iloc[65] == "spike"
    # Flat region (iloc 10): no threshold crossed -> range_bound
    assert labels.iloc[10] == "range_bound"


def test_make_regime_labels_known_regimes_override() -> None:
    from src.services.tabpfn import _make_regime_labels

    index = pd.date_range("2024-01-01", periods=20, freq="D")
    proxy = pd.Series([100.0] * 20, index=index)

    regime_labels = ["trend_up", "range_bound", "trend_down", "spike"]
    thresholds = {"trend_up": 0.15, "trend_down": -0.15, "spike": 0.05}
    known_regimes = [("2024-01-05", "2024-01-10", "trend_down")]

    labels = _make_regime_labels(proxy, index, regime_labels, thresholds, known_regimes)

    assert (labels.loc["2024-01-05":"2024-01-10"] == "trend_down").all()
    assert labels.iloc[0] == "range_bound"
