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
    featurizer_config: dict[str, object]
    conversation: list[object]
    activity_events: list[object]
    stage_history: list[object]
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
    default_featurizer_config: dict[str, object]
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


class ProceedRequest(BaseModel):
    featurizer_config_patch: dict[str, object] | None = None


class ProceedResponse(BaseModel):
    session_id: str


class RerunRequest(BaseModel):
    stage: str
    featurizer_config_patch: dict[str, object] | None = None


class RerunResponse(BaseModel):
    session_id: str


class CancelResponse(BaseModel):
    session_id: str
    stage: str
    status: str


class UploadResponse(BaseModel):
    artifact_id: str


class SeriesPoint(BaseModel):
    date: str
    value: float | None


class DataArtifactDetail(BaseModel):
    kind: str = "data"
    artifact_id: str
    round: int
    sources: list[object]
    data_manifest: dict[str, object]
    series_preview: dict[str, list[SeriesPoint]]
    cache_hit: bool
    cached_from_session_id: str | None


class ConnectorOut(BaseModel):
    id: str
    name: str
    description: str
    type: str
    available: bool


class ConnectorCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    spec: dict[str, object]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    session_id: str
