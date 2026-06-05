from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

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

    # Snapshot all fields before any async calls that could expire s
    user_conversation = [*s.conversation, {"role": "user", "content": req.message}]
    current_stage = s.stage
    current_pending = list(s.pending_sources or [])
    current_featurizer_config = dict(s.featurizer_config or {})
    current_activity_events = list(s.activity_events or [])
    current_stage_history = list(s.stage_history or [])

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
    try:
        result = await interpreter.interpret(
            message=req.message,
            session_stage=current_stage,
            conversation=user_conversation,
            data_manifest=data_manifest,
        )
    except Exception as exc:
        log.error("chat.interpret_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Interpreter error: {exc}") from exc

    action = result.get("action", "advance")
    reply = result.get("reply", "")
    updates = result.get("updates", {})
    now = datetime.now(UTC)

    # All writes use only snapshots — transition_stage/set_status read s.*
    # which would trigger MissingGreenlet after the LLM await. Inline instead.
    chat_event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "created_at": now.isoformat(),
        "type": "chat_reply",
        "action": action,
        "reply": reply,
    }
    s.conversation = [*user_conversation, {"role": "assistant", "content": reply}]
    s.activity_events = [*current_activity_events, chat_event]
    s.updated_at = now.replace(tzinfo=None)

    if action == "advance":
        s.stage = SessionStage.FEATURIZING.value
        s.stage_history = [
            *current_stage_history,
            {"stage": SessionStage.FEATURIZING.value, "entered_at": now.isoformat()},
        ]
        s.status = SessionStatus.RUNNING.value
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    elif action == "refetch":
        sources_to_add = updates.get("sources_to_add", [])
        s.pending_sources = [
            *current_pending,
            *[{"connector_id": sid, "params": {}} for sid in sources_to_add],
        ]
        s.stage = SessionStage.DATA_GATHERING.value
        s.stage_history = [
            *current_stage_history,
            {"stage": SessionStage.DATA_GATHERING.value, "entered_at": now.isoformat()},
        ]
        s.status = SessionStatus.RUNNING.value
        await db.commit()
        background_tasks.add_task(_run_data_agent_background, uid)

    elif action == "update_config":
        config_patch = updates.get("featurizer_config_patch", {})
        s.featurizer_config = {**current_featurizer_config, **config_patch}
        s.stage = SessionStage.FEATURIZING.value
        s.stage_history = [
            *current_stage_history,
            {"stage": SessionStage.FEATURIZING.value, "entered_at": now.isoformat()},
        ]
        s.status = SessionStatus.RUNNING.value
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    else:
        s.stage_history = current_stage_history
        await db.commit()

    log.info("chat.handled", session_id=session_id, action=action)
    return ChatResponse(session_id=session_id)
