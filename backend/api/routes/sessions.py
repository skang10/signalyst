from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import (
    AnalysisResultRef,
    CreateSessionRequest,
    CreateSessionResponse,
    DataArtifactRef,
    FeatureArtifactRef,
    SessionArtifacts,
    SessionDetail,
    SessionListItem,
)
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact
from src.db.models import Session as SessionModel
from src.db.session import get_session

router = APIRouter(tags=["sessions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _iso(dt: object) -> str:
    return dt.isoformat() if dt is not None else ""  # type: ignore[union-attr]


async def _build_artifacts(db: AsyncSession, session_id: uuid.UUID) -> SessionArtifacts:
    data_rows = (
        (await db.execute(select(DataArtifact).where(DataArtifact.session_id == session_id)))
        .scalars()
        .all()
    )
    feature_rows = (
        (await db.execute(select(FeatureArtifact).where(FeatureArtifact.session_id == session_id)))
        .scalars()
        .all()
    )
    analysis_rows = (
        (await db.execute(select(AnalysisResult).where(AnalysisResult.session_id == session_id)))
        .scalars()
        .all()
    )

    return SessionArtifacts(
        data=[
            DataArtifactRef(
                artifact_id=str(r.id),
                round=r.round,
                cache_hit=r.cache_hit,
                created_at=_iso(r.created_at),
            )
            for r in data_rows
        ],
        features=[
            FeatureArtifactRef(
                artifact_id=str(r.id),
                cache_hit=r.cache_hit,
                created_at=_iso(r.created_at),
            )
            for r in feature_rows
        ],
        analysis=[
            AnalysisResultRef(
                artifact_id=str(r.id),
                cache_hit=r.cache_hit,
                has_summary=r.summary is not None,
                created_at=_iso(r.created_at),
            )
            for r in analysis_rows
        ],
    )


def _to_detail(s: SessionModel, artifacts: SessionArtifacts) -> SessionDetail:
    return SessionDetail(
        session_id=str(s.id),
        market_profile=s.market_profile,
        timeframe_start=str(s.timeframe_start),
        timeframe_end=str(s.timeframe_end),
        stage=s.stage,
        status=s.status,
        error=s.error,
        auto=s.auto,
        featurizer_config=s.featurizer_config,
        conversation=s.conversation,
        activity_events=s.activity_events,
        stage_history=s.stage_history,
        artifacts=artifacts,
        created_at=_iso(s.created_at),
        updated_at=_iso(s.updated_at),
    )


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_session(req: CreateSessionRequest, db: SessionDep) -> CreateSessionResponse:
    s = SessionModel(
        market_profile=req.market_profile,
        timeframe_start=date.fromisoformat(req.timeframe_start),
        timeframe_end=date.fromisoformat(req.timeframe_end),
        auto=req.auto,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return CreateSessionResponse(session_id=str(s.id))


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(db: SessionDep) -> list[SessionListItem]:
    rows = (
        (await db.execute(select(SessionModel).order_by(SessionModel.created_at.desc()).limit(100)))
        .scalars()
        .all()
    )
    return [
        SessionListItem(
            session_id=str(s.id),
            market_profile=s.market_profile,
            timeframe_start=str(s.timeframe_start),
            timeframe_end=str(s.timeframe_end),
            stage=s.stage,
            status=s.status,
            created_at=_iso(s.created_at),
            updated_at=_iso(s.updated_at),
        )
        for s in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str, db: SessionDep) -> SessionDetail:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    artifacts = await _build_artifacts(db, uid)
    return _to_detail(s, artifacts)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: SessionDep) -> dict:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(s)
    await db.commit()
    return {"session_id": session_id}
