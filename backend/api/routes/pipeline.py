from __future__ import annotations

import hashlib
import io
import pathlib
import uuid
from datetime import date
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
from sqlmodel import delete, select

from api.models import (
    CancelResponse,
    ConfigPatchRequest,
    ConfigPatchResponse,
    DataArtifactDetail,
    ProceedRequest,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
from src.db.models import DataArtifact, SessionStage, SessionStatus, UploadedSource
from src.db.models import Session as SessionModel
from src.db.session import engine, get_session
from src.services.featurizer_config import apply_config_patch
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


_MIN_ROWS = 70  # max(windows=60) + max(lags=20) + 10 for default oil config


def _parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buf)
    else:
        df = pd.read_csv(buf)

    # Validation 1: parseable date index
    _NO_DATE_MSG = "No parseable date column found. Include a 'date' column in YYYY-MM-DD format."
    if "date" in df.columns:
        df = df.set_index("date")
    elif not isinstance(df.index, pd.DatetimeIndex):
        # Only try to parse if the index looks like strings, not integers
        if df.index.dtype == object or str(df.index.dtype).startswith("datetime"):
            try:
                df.index = pd.DatetimeIndex(df.index)
            except Exception:
                raise ValueError(_NO_DATE_MSG)
        else:
            raise ValueError(_NO_DATE_MSG)
    try:
        df.index = pd.DatetimeIndex(df.index)
    except Exception:
        raise ValueError(_NO_DATE_MSG)

    df = df.sort_index()
    df = df.select_dtypes(include="number")

    # Validation 2: minimum row count
    if len(df) < _MIN_ROWS:
        raise ValueError(f"Uploaded file has {len(df)} rows; at least {_MIN_ROWS} are required.")

    return df


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


async def _run_data_agent_background(session_id: uuid.UUID) -> None:
    from src.services.data_agent import run_data_agent_service
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_data_agent_service(session_id, engine)
    await run_featurizer_service(session_id, engine)
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
    mode: str = Form(default="merge"),
) -> UploadResponse:
    uid, s = await _get_session_or_404(session_id, db)

    content = await file.read()
    if len(content) > _UPLOAD_SIZE_LIMIT:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    try:
        df = _parse_upload(content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if df.empty:
        raise HTTPException(status_code=422, detail="No numeric columns found in uploaded file")

    upload_only_df = df

    file_hash = hashlib.sha256(content).hexdigest()[:16]
    source_hash = stable_hash(f"upload:{source_name}:{file_hash}")
    data_manifest = _build_manifest(df)

    # Validation 3: date range overlap warning (non-blocking)
    warnings: list[str] = []
    upload_start = df.index.min().date()
    upload_end = df.index.max().date()
    if upload_end < s.timeframe_start or upload_start > s.timeframe_end:
        warnings.append(
            f"Uploaded date range {upload_start}–{upload_end} does not overlap with "
            f"session timeframe {s.timeframe_start}–{s.timeframe_end}."
        )

    # Validation 4: oil profile — no WTI column hint (non-blocking)
    wti_cols = [c for c in df.columns if "CL=F" in c or "wti" in c.lower()]
    if not wti_cols and s.market_profile == "oil":
        warnings.append(
            "No column matching 'CL=F' or 'wti' found. "
            "TabPFNService will use the first column as a WTI proxy for regime labelling."
        )

    if warnings:
        data_manifest["warnings"] = warnings

    # Load existing artifact for merge or round-number tracking
    existing = (
        (
            await db.execute(
                select(DataArtifact)
                .where(DataArtifact.session_id == uid)
                .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    round_num = (existing.round + 1) if existing else 1
    prior_sources: list[Any] = list(existing.sources) if (existing and mode == "merge") else []

    if existing is not None and mode == "merge":
        # Load existing raw data into a DataFrame
        if existing.raw_data:
            existing_df = pd.DataFrame(
                {
                    col: pd.Series(v["data"], index=pd.DatetimeIndex(v["index"]), dtype=float)
                    for col, v in existing.raw_data.items()
                }
            )
        elif existing.raw_data_ref:
            existing_df = pd.read_parquet(existing.raw_data_ref)
        else:
            existing_df = pd.DataFrame()

        if not existing_df.empty:
            # Outer join — uploaded columns take precedence on overlap
            merged = existing_df.join(df, how="outer", rsuffix="_upload")
            for col in df.columns:
                dup = f"{col}_upload"
                if dup in merged.columns:
                    merged[col] = merged[dup]
                    merged = merged.drop(columns=[dup])
                else:
                    merged[col] = df[col]
            df = merged.sort_index()

        # Re-build manifest and warnings from merged data
        data_manifest = _build_manifest(df)
        warnings = []
        upload_start = df.index.min().date()
        upload_end = df.index.max().date()
        if upload_end < s.timeframe_start or upload_start > s.timeframe_end:
            warnings.append(
                f"Uploaded date range {upload_start}–{upload_end} does not overlap with "
                f"session timeframe {s.timeframe_start}–{s.timeframe_end}."
            )
        wti_cols = [c for c in df.columns if "CL=F" in c or "wti" in c.lower()]
        if not wti_cols and s.market_profile == "oil":
            warnings.append(
                "No column matching 'CL=F' or 'wti' found. "
                "TabPFNService will use the first column as a WTI proxy for regime labelling."
            )
        if warnings:
            data_manifest["warnings"] = warnings

        # Recompute source_hash from merged content
        merged_bytes = df.to_json().encode()
        source_hash = stable_hash(hashlib.sha256(merged_bytes).hexdigest()[:16])

    artifact_id = uuid.uuid4()
    raw_data: dict[str, Any] | None = None
    raw_data_ref: str | None = None

    merged_bytes_for_size = df.to_json().encode()
    if len(merged_bytes_for_size) <= _RAW_INLINE_THRESHOLD:
        raw_data = _df_to_raw_data(df)
    else:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ref = str(_ARTIFACTS_DIR / f"{artifact_id}.parquet")
        df.to_parquet(ref)
        raw_data_ref = ref

    all_sources = [*prior_sources, {"connector_id": "upload", "source_name": source_name}]

    # Persist the uploaded data on its own (independent of this artifact's lifecycle) so
    # future data-gathering re-runs can re-merge it even after connector sources change.
    upload_raw_data: dict[str, Any] | None = None
    upload_raw_data_ref: str | None = None
    upload_bytes = upload_only_df.to_json().encode()
    if len(upload_bytes) <= _RAW_INLINE_THRESHOLD:
        upload_raw_data = _df_to_raw_data(upload_only_df)
    else:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        upload_ref = str(_ARTIFACTS_DIR / f"{artifact_id}_upload.parquet")
        upload_only_df.to_parquet(upload_ref)
        upload_raw_data_ref = upload_ref

    await db.execute(
        delete(UploadedSource)
        .where(UploadedSource.session_id == uid)  # type: ignore[arg-type]
        .where(UploadedSource.source_name == source_name)  # type: ignore[arg-type]
    )
    db.add(
        UploadedSource(
            session_id=uid,
            source_name=source_name,
            columns=list(upload_only_df.columns),
            raw_data=upload_raw_data,
            raw_data_ref=upload_raw_data_ref,
        )
    )

    # Track this upload in pending_sources so it's included (and toggleable) on future runs
    upload_pending_entry = {
        "connector_id": "upload",
        "source_name": source_name,
        "columns": list(upload_only_df.columns),
    }
    s.pending_sources = [
        *[
            p
            for p in (s.pending_sources or [])
            if not (p.get("connector_id") == "upload" and p.get("source_name") == source_name)
        ],
        upload_pending_entry,
    ]

    a = DataArtifact(
        id=artifact_id,
        session_id=uid,
        round=round_num,
        sources=all_sources,
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
    req: ProceedRequest | None = None,
) -> ProceedResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.stage != SessionStage.USER_REVIEW:
        raise HTTPException(status_code=409, detail=f"proceed not available at stage {s.stage}")
    if s.status == SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409, detail="a task is already running — POST /cancel first"
        )

    # Guard: reject if the latest DataArtifact has too much missing data
    _MAX_MISSING_PCT = 30.0
    latest_artifact = (
        (
            await db.execute(
                select(DataArtifact)
                .where(DataArtifact.session_id == uid)
                .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    if latest_artifact is not None:
        missing_vals = list(latest_artifact.data_manifest.get("missing_pct", {}).values())
        avg_missing = sum(missing_vals) / len(missing_vals) if missing_vals else 0.0
        if avg_missing > _MAX_MISSING_PCT:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Average missing data is {avg_missing:.1f}% (limit {_MAX_MISSING_PCT:.0f}%). "
                    "Fix data quality before running analysis — upload a file with overlapping "
                    "dates or use 'Replace existing data'."
                ),
            )

    if req and req.featurizer_config_patch:
        s.featurizer_config = {**s.featurizer_config, **req.featurizer_config_patch}

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
    elif target == SessionStage.DATA_GATHERING:
        background_tasks.add_task(_run_data_agent_background, uid)

    log.info("session.rerun", session_id=session_id, stage=req.stage)
    return RerunResponse(session_id=session_id)


@router.patch(
    "/sessions/{session_id}/config",
    response_model=ConfigPatchResponse,
)
async def update_config(
    session_id: str,
    req: ConfigPatchRequest,
    db: SessionDep,
) -> ConfigPatchResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if req.featurizer_config_patch is not None:
        if s.stage != SessionStage.USER_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="featurizer config can only be edited during user_review",
            )
        s.featurizer_config = apply_config_patch(s.featurizer_config, req.featurizer_config_patch)

    if req.timeframe_start is not None:
        s.timeframe_start = date.fromisoformat(req.timeframe_start)
    if req.timeframe_end is not None:
        s.timeframe_end = date.fromisoformat(req.timeframe_end)
    if req.pending_sources is not None:
        s.pending_sources = req.pending_sources

    await db.commit()
    log.info("session.config_updated", session_id=session_id)
    return ConfigPatchResponse(session_id=session_id)


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
