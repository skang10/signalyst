from __future__ import annotations

import hashlib
import io
import pathlib
import uuid
from typing import Annotated, Any

import pandas as pd
import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import (
    CancelResponse,
    DataArtifactDetail,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
from src.db.models import DataArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.db.session import engine, get_session
from src.services.hashing import stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

router = APIRouter(tags=["pipeline"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_RERUN_ALLOWED_STAGES: dict[str, SessionStage] = {
    "data_gathering": SessionStage.DATA_GATHERING,
    "featurizing": SessionStage.FEATURIZING,
    "analyzing": SessionStage.ANALYZING,
}
_UPLOAD_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB
_ARTIFACTS_DIR = pathlib.Path("data/artifacts")
_RAW_INLINE_THRESHOLD = 5 * 1024 * 1024  # 5 MB


def _df_to_raw_data(df: pd.DataFrame) -> dict[str, Any]:
    return {
        col: {
            "index": [str(d.date()) for d in df.index],
            "data": [None if pd.isna(v) else float(v) for v in df[col]],
        }
        for col in df.columns
    }


def _build_manifest(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "tickers": list(df.columns),
        "date_range": {
            "start": str(df.index.min().date()),
            "end": str(df.index.max().date()),
        },
        "rows": len(df),
        "missing_pct": {col: round(float(df[col].isna().mean() * 100), 2) for col in df.columns},
        "summary_stats": {
            col: {
                "mean": round(float(df[col].mean(skipna=True)), 4),
                "std": round(float(df[col].std(skipna=True)), 4),
                "min": round(float(df[col].min(skipna=True)), 4),
                "max": round(float(df[col].max(skipna=True)), 4),
            }
            for col in df.columns
        },
    }


def _parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buf)
    else:
        df = pd.read_csv(buf)

    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    df = df.sort_index()
    return df.select_dtypes(include="number")


async def _get_session_or_404(session_id: str, db: AsyncSession) -> tuple[uuid.UUID, SessionModel]:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return uid, s


async def _run_featurizer_background(session_id: uuid.UUID) -> None:
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_featurizer_service(session_id, engine)
    # Chain to TabPFN; it reads current status and exits if featurizer failed/canceled
    await run_tabpfn_service(session_id, engine)


async def _run_tabpfn_background(session_id: uuid.UUID) -> None:
    from src.services.tabpfn import run_tabpfn_service

    await run_tabpfn_service(session_id, engine)


@router.post(
    "/sessions/{session_id}/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_data(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
    file: UploadFile = File(...),
    source_name: str = Form(...),
) -> UploadResponse:
    uid, s = await _get_session_or_404(session_id, db)

    content = await file.read()
    if len(content) > _UPLOAD_SIZE_LIMIT:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    df = _parse_upload(content, file.filename or "")
    if df.empty:
        raise HTTPException(status_code=422, detail="No numeric columns found in uploaded file")

    file_hash = hashlib.sha256(content).hexdigest()[:16]
    source_hash = stable_hash(f"upload:{source_name}:{file_hash}")
    data_manifest = _build_manifest(df)

    artifact_id = uuid.uuid4()
    raw_data: dict[str, Any] | None = None
    raw_data_ref: str | None = None

    if len(content) <= _RAW_INLINE_THRESHOLD:
        raw_data = _df_to_raw_data(df)
    else:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ref = str(_ARTIFACTS_DIR / f"{artifact_id}.parquet")
        df.to_parquet(ref)
        raw_data_ref = ref

    a = DataArtifact(
        id=artifact_id,
        session_id=uid,
        round=1,
        sources=[{"connector_id": "upload", "source_name": source_name}],
        data_manifest=data_manifest,
        raw_data=raw_data,
        raw_data_ref=raw_data_ref,
        source_hash=source_hash,
    )
    db.add(a)

    append_activity_event(
        s,
        {
            "type": "artifact_ready",
            "kind": "data",
            "artifact_id": str(artifact_id),
            "rows": data_manifest["rows"],
            "tickers": data_manifest["tickers"],
        },
    )
    transition_stage(s, SessionStage.USER_REVIEW)
    set_status(s, SessionStatus.WAITING)
    await db.commit()

    log.info(
        "session.upload",
        session_id=session_id,
        source_name=source_name,
        rows=data_manifest["rows"],
        artifact_id=str(artifact_id),
    )
    return UploadResponse(artifact_id=str(artifact_id))


@router.post(
    "/sessions/{session_id}/proceed",
    response_model=ProceedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def proceed(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> ProceedResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.stage != SessionStage.USER_REVIEW:
        raise HTTPException(status_code=409, detail=f"proceed not available at stage {s.stage}")
    if s.status == SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409, detail="a task is already running — POST /cancel first"
        )

    from_stage = s.stage
    transition_stage(s, SessionStage.FEATURIZING)
    set_status(s, SessionStatus.RUNNING)
    append_activity_event(s, {"type": "stage_transition", "from": from_stage, "to": "featurizing"})
    await db.commit()

    background_tasks.add_task(_run_featurizer_background, uid)
    log.info("session.proceed", session_id=session_id)
    return ProceedResponse(session_id=session_id)


@router.post(
    "/sessions/{session_id}/rerun",
    response_model=RerunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun(
    session_id: str,
    req: RerunRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> RerunResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if req.stage not in _RERUN_ALLOWED_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"stage must be one of: {list(_RERUN_ALLOWED_STAGES)}",
        )
    if s.status == SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409, detail="a task is already running — POST /cancel first"
        )

    target = _RERUN_ALLOWED_STAGES[req.stage]
    if req.featurizer_config_patch:
        s.featurizer_config = {**s.featurizer_config, **req.featurizer_config_patch}

    from_stage = s.stage
    transition_stage(s, target)
    set_status(s, SessionStatus.RUNNING)
    append_activity_event(s, {"type": "stage_transition", "from": from_stage, "to": target.value})
    await db.commit()

    if target == SessionStage.FEATURIZING:
        background_tasks.add_task(_run_featurizer_background, uid)
    elif target == SessionStage.ANALYZING:
        background_tasks.add_task(_run_tabpfn_background, uid)

    log.info("session.rerun", session_id=session_id, stage=req.stage)
    return RerunResponse(session_id=session_id)


@router.post("/sessions/{session_id}/cancel", response_model=CancelResponse)
async def cancel(session_id: str, db: SessionDep) -> CancelResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="no task is currently running for this session")

    current_stage = s.stage
    set_status(s, SessionStatus.CANCELED)
    append_activity_event(s, {"type": "canceled", "stage": current_stage})
    await db.commit()

    log.info("session.canceled", session_id=session_id, stage=current_stage)
    return CancelResponse(session_id=session_id, stage=current_stage, status="canceled")


@router.get("/sessions/{session_id}/artifacts/{artifact_id}", response_model=DataArtifactDetail)
async def get_artifact(session_id: str, artifact_id: str, db: SessionDep) -> DataArtifactDetail:
    try:
        s_uid = uuid.UUID(session_id)
        a_uid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    artifact = await db.get(DataArtifact, a_uid)
    if artifact is None or artifact.session_id != s_uid:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # series_preview — max 500 points per series, never expose raw_data directly
    series_preview: dict[str, list[SeriesPoint]] = {}
    if artifact.raw_data:
        for col, v in artifact.raw_data.items():
            pairs = list(zip(v["index"], v["data"]))[:500]
            series_preview[col] = [SeriesPoint(date=d, value=val) for d, val in pairs]
    elif artifact.raw_data_ref:
        df = pd.read_parquet(artifact.raw_data_ref)
        for col in list(df.columns)[:10]:
            series = df[col].dropna().iloc[:500]
            series_preview[col] = [
                SeriesPoint(date=str(idx.date()), value=float(val))
                for idx, val in zip(series.index, series)
            ]

    return DataArtifactDetail(
        artifact_id=str(artifact.id),
        round=artifact.round,
        sources=artifact.sources,
        data_manifest=artifact.data_manifest,
        series_preview=series_preview,
        cache_hit=artifact.cache_hit,
        cached_from_session_id=(
            str(artifact.cached_from_session_id) if artifact.cached_from_session_id else None
        ),
    )
