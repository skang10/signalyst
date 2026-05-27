from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import RunResult
from src.agent import run_agent_loop
from src.agent import tabpfn_progress as _tabpfn_progress
from src.db.models import Run, RunStatus
from src.db.session import get_session

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    date_range_start: str
    date_range_end: str
    tasks: list[str] = ["regime_classification", "price_direction", "equity_outperformance"]
    analysis_mode: Literal["quick", "full"] = "quick"


class AnalyzeResponse(BaseModel):
    run_id: str


class CancelRunResponse(BaseModel):
    run_id: str
    status: RunStatus


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> AnalyzeResponse:
    run = Run(
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
        tasks=request.tasks,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    background_tasks.add_task(
        run_agent_loop,
        run.id,
        request.date_range_start,
        request.date_range_end,
        request.tasks,
        request.analysis_mode,
    )

    return AnalyzeResponse(run_id=str(run.id))


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str, session: SessionDep) -> RunResult:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    run = await session.get(Run, uid)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return RunResult(run_id=str(run.id), status=run.status, result=run.result, error=run.error)


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
async def cancel_run(run_id: str, session: SessionDep) -> CancelRunResponse:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    run = await session.get(Run, uid)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is already terminal")

    run.status = RunStatus.CANCELED
    run.completed_at = datetime.now(UTC).replace(tzinfo=None)
    run.error = "Canceled by user"
    await session.commit()
    _tabpfn_progress.cancel(run_id)

    return CancelRunResponse(run_id=run_id, status=RunStatus.CANCELED)


@router.get("/history", response_model=list[RunResult])
async def get_history(session: SessionDep) -> list[RunResult]:
    result = await session.execute(
        select(Run).order_by(Run.created_at.desc()).limit(20)  # type: ignore[attr-defined]
    )
    runs = result.scalars().all()
    return [RunResult(run_id=str(r.id), status=r.status, result=r.result) for r in runs]
