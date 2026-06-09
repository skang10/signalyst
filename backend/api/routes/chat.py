from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from src.services.featurizer_config import apply_config_patch
from src.services.followup import run_followup_service

router = APIRouter(tags=["chat"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CHAT_ALLOWED_STAGES = {SessionStage.USER_REVIEW.value, SessionStage.FOLLOW_UP.value}


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

    if s.stage == SessionStage.FOLLOW_UP.value:
        now = datetime.now(UTC)
        s.conversation = [
            *s.conversation,
            {"role": "user", "content": req.message, "created_at": now.isoformat()},
        ]
        s.status = SessionStatus.RUNNING.value
        s.updated_at = now.replace(tzinfo=None)
        await db.commit()
        background_tasks.add_task(run_followup_service, uid, engine)
        return ChatResponse(session_id=session_id)

    # Snapshot all fields before any async calls that could expire s
    _req_time = datetime.now(UTC).isoformat()
    user_conversation = [
        *s.conversation,
        {"role": "user", "content": req.message, "created_at": _req_time},
    ]
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
            featurizer_config=current_featurizer_config,
        )
    except Exception as exc:
        log.error("chat.interpret_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Interpreter error: {exc}") from exc

    action = result.get("action", "answer")
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
    s.conversation = [
        *user_conversation,
        {"role": "assistant", "content": reply, "created_at": now.isoformat()},
    ]
    s.activity_events = [*current_activity_events, chat_event]
    s.updated_at = now.replace(tzinfo=None)

    if action == "advance":
        s.stage = SessionStage.FEATURIZING.value
        transition_ts = (now + timedelta(milliseconds=1)).isoformat()
        s.stage_history = [
            *current_stage_history,
            {"stage": SessionStage.FEATURIZING.value, "entered_at": transition_ts},
        ]
        s.status = SessionStatus.RUNNING.value
        # Emit a stage_transition so the activity feed visibly shows the pipeline
        # advancing, instead of silently jumping from review to results.
        advance_transition: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "created_at": transition_ts,
            "type": "stage_transition",
            "from": SessionStage.USER_REVIEW.value,
            "to": SessionStage.FEATURIZING.value,
        }
        s.activity_events = [*current_activity_events, chat_event, advance_transition]
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    elif action == "refetch":
        sources_to_add = updates.get("sources_to_add", [])
        s.pending_sources = [
            *current_pending,
            *[{"connector_id": sid, "params": {}} for sid in sources_to_add],
        ]
        s.stage = SessionStage.DATA_GATHERING.value
        refetch_ts = (now + timedelta(milliseconds=1)).isoformat()
        s.stage_history = [
            *current_stage_history,
            {"stage": SessionStage.DATA_GATHERING.value, "entered_at": refetch_ts},
        ]
        s.status = SessionStatus.RUNNING.value
        # Emit a stage_transition so buildGroups opens a fresh Data Gathering group.
        # +1ms ensures the agent's reply (at `now`) sorts before this transition.
        refetch_transition: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "created_at": refetch_ts,
            "type": "stage_transition",
            "from": SessionStage.USER_REVIEW.value,
            "to": SessionStage.DATA_GATHERING.value,
        }
        s.activity_events = [*current_activity_events, chat_event, refetch_transition]
        await db.commit()
        background_tasks.add_task(_run_data_agent_background, uid)

    elif action == "update_config":
        # Patch the config but stay in USER_REVIEW — only an explicit "advance"
        # starts the pipeline. This guarantees changing a setting can never by
        # itself trigger a run, regardless of how the LLM phrases its reply.
        raw_patch = updates.get("featurizer_config_patch", {})
        s.featurizer_config = apply_config_patch(current_featurizer_config, raw_patch)
        s.stage_history = current_stage_history
        await db.commit()

    else:
        s.stage_history = current_stage_history
        await db.commit()

    log.info("chat.handled", session_id=session_id, action=action)
    return ChatResponse(session_id=session_id)
