from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON as SAJson
from sqlalchemy import Column
from sqlalchemy import String as SAString
from sqlmodel import Field, SQLModel


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class Run(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: RunStatus = Field(default=RunStatus.PENDING, sa_column=Column(SAString, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    completed_at: datetime | None = Field(default=None)
    date_range_start: str
    date_range_end: str
    tasks: list[str] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    error: str | None = Field(default=None)
