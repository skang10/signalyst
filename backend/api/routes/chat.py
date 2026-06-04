from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from starlette import status

from api.models import ChatRequest, ChatResponse
from src.agents.review_interpreter import ReviewInterpreter
from src.db.models import DataArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.db.session import engine, get_session
from src.services.stage import append_activity_event, set_status, transition_stage

router = APIRouter(tags=["chat"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CHAT_ALLOWED_STAGES = {SessionStage.USER_REVIEW.value}


async def _run_featurizer_background(session_id: uuid.UUID) -> None:
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)


async def _run_data_agent_background(session_id: uuid.UUID) -> None:
    from src.services.data_agent import run_data_agent_service
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_data_agent_service(session_id, engine)
    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def chat(
    session_id: str,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> ChatResponse:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")

    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.stage not in _CHAT_ALLOWED_STAGES:
        raise HTTPException(status_code=409, detail=f"chat not available at stage {s.stage}")

    # Snapshot what we need before any async calls that could expire s
    user_conversation = [*s.conversation, {"role": "user", "content": req.message}]
    current_stage = s.stage
    current_pending = list(s.pending_sources or [])
    current_featurizer_config = dict(s.featurizer_config or {})
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
    data_manifest = latest_artifact.data_manifest if latest_artifact else {}

    interpreter = ReviewInterpreter()
    result = await interpreter.interpret(
        message=req.message,
        session_stage=current_stage,
        conversation=user_conversation,
        data_manifest=data_manifest,
    )

    action = result.get("action", "advance")
    reply = result.get("reply", "")
    updates = result.get("updates", {})

    # Re-fetch s to avoid working with expired state after awaits
    await db.refresh(s)
    s.conversation = [*user_conversation, {"role": "assistant", "content": reply}]
    append_activity_event(s, {"type": "chat_reply", "action": action, "reply": reply})

    if action == "advance":
        transition_stage(s, SessionStage.FEATURIZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    elif action == "refetch":
        sources_to_add = updates.get("sources_to_add", [])
        if sources_to_add:
            s.pending_sources = [
                *current_pending,
                *[{"connector_id": sid, "params": {}} for sid in sources_to_add],
            ]
        transition_stage(s, SessionStage.DATA_GATHERING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_data_agent_background, uid)

    elif action == "update_config":
        config_patch = updates.get("featurizer_config_patch", {})
        if config_patch:
            s.featurizer_config = {**current_featurizer_config, **config_patch}
        transition_stage(s, SessionStage.FEATURIZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    else:
        await db.commit()

    log.info("chat.handled", session_id=session_id, action=action)
    return ChatResponse(session_id=session_id)
