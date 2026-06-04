from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.db.models import Session, SessionStage, SessionStatus


def transition_stage(session: Session, new_stage: SessionStage) -> None:
    """Update session.stage and append to stage_history. Call before db.commit()."""
    session.stage = new_stage.value
    session.stage_history = [
        *session.stage_history,
        {"stage": new_stage.value, "entered_at": datetime.now(UTC).isoformat()},
    ]
    session.updated_at = datetime.now(UTC).replace(tzinfo=None)


def set_status(session: Session, status: SessionStatus, error: str | None = None) -> None:
    session.status = status.value
    if error is not None:
        session.error = error
    session.updated_at = datetime.now(UTC).replace(tzinfo=None)


def append_activity_event(session: Session, event: dict[str, Any]) -> None:
    """Append an event to activity_events with auto-generated event_id and created_at."""
    enriched: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        **event,
    }
    session.activity_events = [*session.activity_events, enriched]
