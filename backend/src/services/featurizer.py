from __future__ import annotations

import hashlib
import io
import json
import pathlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from src.config import settings
from src.db.models import DataArtifact, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.featurizer import TimeSeriesFeaturizer
from src.services.hashing import canonical_json, stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()

Publisher = Callable[[dict[str, Any]], Awaitable[None]]

_ARTIFACTS_DIR = pathlib.Path("data/artifacts")


def _raw_data_to_series(raw_data: dict[str, Any]) -> dict[str, pd.Series]:
    return {
        col: pd.Series(
            v["data"],
            index=pd.DatetimeIndex(v["index"]),
            name=col,
            dtype=float,
        )
        for col, v in raw_data.items()
    }


def _raw_data_ref_to_series(ref: str) -> dict[str, pd.Series]:
    df = pd.read_parquet(ref)
    return {col: df[col].rename(col) for col in df.columns}


async def run_featurizer_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    session_id_str = str(session_id)
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{session_id_str}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        async with AsyncSession(engine) as db:
            s = await db.get(SessionModel, session_id)
            if s is None:
                log.error("featurizer.session_not_found", session_id=session_id_str)
                return
            if s.status == SessionStatus.CANCELED:
                log.info("featurizer.canceled", session_id=session_id_str)
                return
            if s.stage != SessionStage.FEATURIZING:
                log.info("featurizer.wrong_stage", session_id=session_id_str, stage=s.stage)
                return

            try:
                await _run(s, db, engine, publisher)
            except Exception as exc:
                log.error("featurizer.failed", session_id=session_id_str, error=str(exc))
                set_status(s, SessionStatus.FAILED, error=str(exc))
                err_event: dict[str, Any] = {
                    "type": "error",
                    "stage": "featurizing",
                    "message": str(exc),
                }
                append_activity_event(s, err_event)
                await db.commit()
                await publisher(err_event)
    finally:
        await r.aclose()  # type: ignore[attr-defined]


async def _run(
    s: SessionModel, db: AsyncSession, engine: AsyncEngine, publisher: Publisher
) -> None:
    session_id = s.id
    cfg = s.featurizer_config

    # Load latest DataArtifact
    stmt = (
        select(DataArtifact)
        .where(DataArtifact.session_id == session_id)
        .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
    )
    data_artifact = (await db.execute(stmt)).scalars().first()
    if data_artifact is None:
        raise ValueError("no DataArtifact found for session")

    config_hash = stable_hash(data_artifact.source_hash, canonical_json(cfg))

    # Within-session cache check
    existing = (
        (
            await db.execute(
                select(FeatureArtifact)
                .where(FeatureArtifact.session_id == session_id)
                .where(FeatureArtifact.config_hash == config_hash)
            )
        )
        .scalars()
        .first()
    )

    if existing is not None:
        log.info("featurizer.cache_hit", session_id=str(session_id), config_hash=config_hash)
        append_activity_event(s, {"type": "cache_hit", "stage": "featurizing"})
        transition_stage(s, SessionStage.ANALYZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        await publisher({"type": "stage_transition", "from": "featurizing", "to": "analyzing"})
        return

    # Reconstruct series_dict
    if data_artifact.raw_data:
        series_dict = _raw_data_to_series(data_artifact.raw_data)
    elif data_artifact.raw_data_ref:
        series_dict = _raw_data_ref_to_series(data_artifact.raw_data_ref)
    else:
        raise ValueError("DataArtifact has neither raw_data nor raw_data_ref")

    featurizer = TimeSeriesFeaturizer(
        windows=cfg.get("windows", [5, 20, 60]),
        lags=cfg.get("lags", [1, 5, 20]),
        feature_families=cfg.get("feature_families"),
        energy_specific=bool(cfg.get("energy_specific", False)),
    )
    features = featurizer.transform(series_dict)

    if features.empty:
        raise ValueError("featurizer produced empty feature matrix — insufficient data")

    log.info(
        "featurizer.complete",
        session_id=str(session_id),
        rows=len(features),
        cols=len(features.columns),
    )

    # Write feature matrix to parquet
    artifact_id = uuid.uuid4()
    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ref = str(_ARTIFACTS_DIR / f"{artifact_id}_features.parquet")
    features.to_parquet(ref)
    matrix_buf = io.BytesIO()
    features.to_parquet(matrix_buf)
    matrix_hash = hashlib.sha256(matrix_buf.getvalue()).hexdigest()[:24]

    # Build feature_manifest
    families: dict[str, int] = {}
    for col in features.columns:
        if any(tag in col for tag in ("_mean_", "_std_", "_min_", "_max_")):
            families["rolling_stats"] = families.get("rolling_stats", 0) + 1
        elif "_lag_" in col:
            families["lag"] = families.get("lag", 0) + 1
        elif "_roc_" in col:
            families["momentum"] = families.get("momentum", 0) + 1
    feature_manifest: dict[str, Any] = {
        "n_features": len(features.columns),
        "n_rows": len(features),
        "feature_families": families,
        "columns": list(features.columns),
    }

    fa = FeatureArtifact(
        id=artifact_id,
        session_id=session_id,
        data_artifact_id=data_artifact.id,
        featurizer_config_snapshot=dict(cfg),
        feature_manifest=feature_manifest,
        feature_matrix_ref=ref,
        matrix_hash=matrix_hash,
        config_hash=config_hash,
    )

    # Guard: check for cancellation that arrived while we were computing
    async with AsyncSession(engine) as check_db:
        fresh = await check_db.get(SessionModel, s.id)
        if fresh is None or fresh.status == SessionStatus.CANCELED:
            log.info("featurizer.canceled_midrun", session_id=str(s.id))
            return

    db.add(fa)
    feat_event: dict[str, Any] = {
        "type": "artifact_ready",
        "kind": "features",
        "artifact_id": str(artifact_id),
        "n_features": len(features.columns),
        "n_rows": len(features),
    }
    append_activity_event(s, feat_event)
    transition_stage(s, SessionStage.ANALYZING)
    set_status(s, SessionStatus.RUNNING)
    await db.commit()
    await publisher(feat_event)
