from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from src.config import settings
from src.db.models import AnalysisResult, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.hashing import canonical_json, stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()

# Heuristic regime labels (same as demo.py — source of truth)
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),
    ("2020-02-01", "2020-10-31", "bust"),
    ("2021-01-01", "2022-06-30", "bull_supercycle"),
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),
]


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


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two 1-D arrays."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf
    exp_counts = np.histogram(expected, bins=breakpoints)[0]
    act_counts = np.histogram(actual, bins=breakpoints)[0]
    exp_pct = (exp_counts + 0.001) / len(expected)
    act_pct = (act_counts + 0.001) / len(actual)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def _detect_drift(features: pd.DataFrame, split: int) -> dict[str, Any]:
    train = features.iloc[:split]
    test = features.iloc[split:]
    if len(test) < 5:
        return {"drift_detected": False, "psi_score": 0.0, "drifted_features": []}
    psi_scores = {
        col: _psi(train[col].dropna().to_numpy(), test[col].dropna().to_numpy())
        for col in features.columns
    }
    drifted = [col for col, psi in psi_scores.items() if psi > 0.20]
    overall = float(np.mean(list(psi_scores.values())))
    return {
        "drift_detected": len(drifted) > 0,
        "psi_score": round(overall, 4),
        "drifted_features": drifted[:10],
    }


async def run_tabpfn_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("tabpfn.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            log.info("tabpfn.canceled", session_id=str(session_id))
            return
        if s.stage != SessionStage.ANALYZING:
            log.info("tabpfn.wrong_stage", session_id=str(session_id), stage=s.stage)
            return

        try:
            await _run(s, db, engine)
        except Exception as exc:
            log.error("tabpfn.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(s, {"type": "error", "stage": "analyzing", "message": str(exc)})
            await db.commit()


async def _run(s: SessionModel, db: AsyncSession, engine: AsyncEngine) -> None:
    session_id = s.id

    stmt = (
        select(FeatureArtifact)
        .where(FeatureArtifact.session_id == session_id)
        .order_by(FeatureArtifact.created_at.desc())  # type: ignore[attr-defined]
    )
    fa = (await db.execute(stmt)).scalars().first()
    if fa is None:
        raise ValueError("no FeatureArtifact found for session")

    regime_labels = ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]
    analysis_config: dict[str, Any] = {}
    feature_hash = stable_hash(
        fa.matrix_hash,
        canonical_json(regime_labels),
        canonical_json(analysis_config),
    )

    # Within-session cache check
    existing = (
        (
            await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.session_id == session_id)
                .where(AnalysisResult.feature_hash == feature_hash)
            )
        )
        .scalars()
        .first()
    )

    if existing is not None:
        log.info("tabpfn.cache_hit", session_id=str(session_id))
        append_activity_event(s, {"type": "cache_hit", "stage": "analyzing"})
        transition_stage(s, SessionStage.FOLLOW_UP)
        set_status(s, SessionStatus.WAITING)
        await db.commit()
        return

    features = pd.read_parquet(fa.feature_matrix_ref)
    split = int(len(features) * 0.8)
    drift = _detect_drift(features, split)

    regime_result: dict[str, Any] | None = None
    direction_result: dict[str, Any] | None = None

    if settings.tabpfn_token:
        try:
            from src.inference import DirectionClassifier, OilRegimeClassifier

            X_train, X_test = features.iloc[:split], features.iloc[split:]

            # Pick WTI proxy column for labeling
            wti_col = next(
                (c for c in features.columns if "CL=F" in c or "wti" in c.lower()),
                features.columns[0],
            )
            wti_proxy = features[wti_col]

            regime_labels_series = _make_regime_labels(wti_proxy, features.index)
            direction_labels_series = _make_direction_labels(wti_proxy, features.index)
            common_idx = features.index.intersection(direction_labels_series.index)
            X_train_dir = features.loc[common_idx[: len(common_idx) * 4 // 5]]
            y_dir_train = direction_labels_series.loc[common_idx[: len(common_idx) * 4 // 5]]

            regime_clf = OilRegimeClassifier(n_estimators=4)
            regime_clf.fit(X_train, regime_labels_series.iloc[:split])
            regime_pred = regime_clf.predict(X_test)
            regime_proba = regime_clf.predict_proba(X_test)
            top_regime = str(regime_pred.value_counts().idxmax())
            top_conf = round(float(regime_proba[top_regime].mean()), 4)
            regime_result = {
                "regime": top_regime,
                "confidence": top_conf,
                "distribution": regime_pred.value_counts().to_dict(),
            }

            dir_clf = DirectionClassifier(n_estimators=4)
            dir_clf.fit(X_train_dir, y_dir_train)
            X_test_dir = features.loc[common_idx[len(common_idx) * 4 // 5 :]]
            dir_pred = dir_clf.predict(X_test_dir)
            dir_proba = dir_clf.predict_proba(X_test_dir)
            top_dir = str(dir_pred.value_counts().idxmax())
            top_dir_conf = round(float(dir_proba[top_dir].mean()), 4)
            direction_result = {
                "direction": top_dir,
                "confidence": top_dir_conf,
                "distribution": dir_pred.value_counts().to_dict(),
            }

            log.info(
                "tabpfn.complete",
                session_id=str(session_id),
                regime=top_regime,
                direction=top_dir,
            )
        except Exception as exc:
            log.warning("tabpfn.inference_failed", session_id=str(session_id), error=str(exc))
    else:
        log.info("tabpfn.skipped_no_token", session_id=str(session_id))

    artifact_id = uuid.uuid4()
    ar = AnalysisResult(
        id=artifact_id,
        session_id=session_id,
        feature_artifact_id=fa.id,
        regime=regime_result,
        direction=direction_result,
        drift=drift,
        feature_hash=feature_hash,
    )

    # Guard: check for cancellation that arrived while we were computing
    async with AsyncSession(engine) as check_db:
        fresh = await check_db.get(SessionModel, s.id)
        if fresh is None or fresh.status == SessionStatus.CANCELED:
            log.info("tabpfn.canceled_midrun", session_id=str(s.id))
            return

    db.add(ar)
    append_activity_event(
        s,
        {
            "type": "artifact_ready",
            "kind": "analysis",
            "artifact_id": str(artifact_id),
            "regime": regime_result.get("regime") if regime_result else None,
        },
    )
    # PR 2: skip EXPLAINING (ExplanationAgent is PR 4), go straight to FOLLOW_UP
    transition_stage(s, SessionStage.FOLLOW_UP)
    set_status(s, SessionStatus.WAITING)
    await db.commit()
