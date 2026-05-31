from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import RunResult
from src.agent import run_agent_continuation, run_agent_loop
from src.agent import tabpfn_progress as _tabpfn_progress
from src.agent.loop import build_system_prompt, format_result_context
from src.db.models import Run, RunStatus
from src.db.session import get_session

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    date_range_start: str
    date_range_end: str
    tasks: list[str] = ["regime_classification", "price_direction", "equity_outperformance"]
    analysis_mode: Literal["quick", "full"] = "quick"
    pre_messages: list[str] = []


class AnalyzeResponse(BaseModel):
    run_id: str


class CancelRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class ContinueRequest(BaseModel):
    message: str


class ContinueResponse(BaseModel):
    run_id: str


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
        pre_messages=request.pre_messages,
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


@router.post(
    "/runs/{run_id}/continue",
    response_model=ContinueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def continue_run(
    run_id: str,
    request: ContinueRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> ContinueResponse:
    try:
        source_uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    source_run = await session.get(Run, source_uid)
    if source_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if source_run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Source run is not completed"
        )
    if source_run.result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source run has no result")

    # Read all attributes before the commit — SQLAlchemy expires objects after commit,
    # and lazy-loading in an async context raises MissingGreenlet.
    src_result = source_run.result
    src_date_start = source_run.date_range_start
    src_date_end = source_run.date_range_end
    src_tasks = list(source_run.tasks)

    context_str = format_result_context(src_result, src_date_start, src_date_end)
    messages: list[dict] = [  # type: ignore[type-arg]
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": context_str},
        {"role": "user", "content": request.message},
    ]

    new_run = Run(
        date_range_start=src_date_start,
        date_range_end=src_date_end,
        tasks=src_tasks,
    )
    session.add(new_run)
    await session.commit()
    await session.refresh(new_run)

    background_tasks.add_task(
        run_agent_continuation,
        new_run.id,
        messages,
        src_date_start,
        src_date_end,
    )

    return ContinueResponse(run_id=str(new_run.id))


@router.get("/history", response_model=list[RunResult])
async def get_history(session: SessionDep) -> list[RunResult]:
    result = await session.execute(
        select(Run).order_by(Run.created_at.desc()).limit(20)  # type: ignore[attr-defined]
    )
    runs = result.scalars().all()
    return [RunResult(run_id=str(r.id), status=r.status, result=r.result) for r in runs]
