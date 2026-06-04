from __future__ import annotations

from pydantic import BaseModel


class DataArtifactRef(BaseModel):
    artifact_id: str
    round: int
    cache_hit: bool
    created_at: str


class FeatureArtifactRef(BaseModel):
    artifact_id: str
    cache_hit: bool
    created_at: str


class AnalysisResultRef(BaseModel):
    artifact_id: str
    cache_hit: bool
    has_summary: bool
    created_at: str


class SessionArtifacts(BaseModel):
    data: list[DataArtifactRef]
    features: list[FeatureArtifactRef]
    analysis: list[AnalysisResultRef]


class SessionListItem(BaseModel):
    session_id: str
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    stage: str
    status: str
    created_at: str
    updated_at: str


class SessionDetail(BaseModel):
    session_id: str
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    stage: str
    status: str
    error: str | None
    auto: bool
    featurizer_config: dict
    conversation: list
    activity_events: list
    stage_history: list
    artifacts: SessionArtifacts
    created_at: str
    updated_at: str


class CreateSessionRequest(BaseModel):
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    auto: bool = False


class CreateSessionResponse(BaseModel):
    session_id: str


class ProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    default_connectors: list[str]
    default_featurizer_config: dict
    regime_labels: list[str]


class IndicatorValue(BaseModel):
    price: float
    change_pct: float


class GprValue(BaseModel):
    value: float
    change_pct: float


class MarketSnapshotResponse(BaseModel):
    wti: IndicatorValue | None = None
    brent: IndicatorValue | None = None
    dxy: IndicatorValue | None = None
    gpr: GprValue | None = None
    eia_inventory_change_mmbbl: float | None = None
    fetched_at: str
