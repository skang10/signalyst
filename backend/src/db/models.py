from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON as SAJson
from sqlalchemy import Column
from sqlalchemy import String as SAString
from sqlmodel import Field, SQLModel


class SessionStage(StrEnum):
    CONFIGURING = "configuring"
    DATA_GATHERING = "data_gathering"
    USER_REVIEW = "user_review"
    FEATURIZING = "featurizing"
    ANALYZING = "analyzing"
    EXPLAINING = "explaining"
    FOLLOW_UP = "follow_up"


class SessionStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    FAILED = "failed"
    CANCELED = "canceled"


class Session(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    market_profile: str
    timeframe_start: date
    timeframe_end: date
    stage: str = Field(
        default=SessionStage.CONFIGURING,
        sa_column=Column(SAString, nullable=False),
    )
    status: str = Field(
        default=SessionStatus.WAITING,
        sa_column=Column(SAString, nullable=False),
    )
    error: str | None = Field(default=None)
    auto: bool = Field(default=False)
    featurizer_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    pending_sources: list[Any] = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    conversation: list[Any] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    activity_events: list[Any] = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    stage_history: list[Any] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DataArtifact(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="session.id")
    round: int = Field(default=1)
    sources: list[Any] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    data_manifest: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    raw_data: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    raw_data_ref: str | None = Field(default=None)
    source_hash: str = Field(default="")
    cached_from_session_id: uuid.UUID | None = Field(default=None)
    cached_from_artifact_id: uuid.UUID | None = Field(default=None)
    cache_hit: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeatureArtifact(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="session.id")
    data_artifact_id: uuid.UUID = Field(foreign_key="dataartifact.id")
    featurizer_config_snapshot: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    feature_manifest: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    feature_matrix_ref: str = Field(default="")
    matrix_hash: str = Field(default="")
    config_hash: str = Field(default="")
    cached_from_session_id: uuid.UUID | None = Field(default=None)
    cached_from_artifact_id: uuid.UUID | None = Field(default=None)
    cache_hit: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisResult(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="session.id")
    feature_artifact_id: uuid.UUID = Field(foreign_key="featureartifact.id")
    regime: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    direction: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    feature_importance: dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    drift: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    backtest: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    summary: str | None = Field(default=None)
    feature_hash: str = Field(default="")
    cached_from_session_id: uuid.UUID | None = Field(default=None)
    cached_from_artifact_id: uuid.UUID | None = Field(default=None)
    cache_hit: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConnectorType(StrEnum):
    BUILTIN = "builtin"
    SPEC = "spec"
    GENERATED = "generated"


class Connector(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    type: str = Field(
        default=ConnectorType.BUILTIN,
        sa_column=Column(SAString, nullable=False),
    )
    spec: dict[str, Any] | None = Field(default=None, sa_column=Column(SAJson, nullable=True))
    code: str | None = Field(default=None)
    tests: str | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MarketProfile(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    default_connectors: list[str] = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    default_featurizer_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    regime_labels: list[str] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
