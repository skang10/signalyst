from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.db.models import (
    Connector,
    ConnectorType,
    DataArtifact,
    MarketProfile,
    SessionStage,
    SessionStatus,
)
from src.db.models import Session as SessionModel


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


def test_session_default_stage_and_status(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
    assert s.stage == SessionStage.CONFIGURING
    assert s.status == SessionStatus.WAITING
    assert s.auto is False
    assert s.featurizer_config == {}
    assert s.conversation == []
    assert s.activity_events == []
    assert s.stage_history == []


def test_session_id_is_uuid(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
    assert isinstance(s.id, uuid.UUID)


def test_session_stage_values():
    assert SessionStage.CONFIGURING == "configuring"
    assert SessionStage.DATA_GATHERING == "data_gathering"
    assert SessionStage.USER_REVIEW == "user_review"
    assert SessionStage.FEATURIZING == "featurizing"
    assert SessionStage.ANALYZING == "analyzing"
    assert SessionStage.EXPLAINING == "explaining"
    assert SessionStage.FOLLOW_UP == "follow_up"


def test_session_status_values():
    assert SessionStatus.RUNNING == "running"
    assert SessionStatus.WAITING == "waiting"
    assert SessionStatus.FAILED == "failed"
    assert SessionStatus.CANCELED == "canceled"


def test_data_artifact_defaults(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
        a = DataArtifact(session_id=s.id, source_hash="abc123")
        session.add(a)
        session.commit()
        session.refresh(a)
    assert a.round == 1
    assert a.cache_hit is False
    assert a.raw_data is None
    assert isinstance(a.id, uuid.UUID)


def test_market_profile_stores_regime_labels(engine):
    with Session(engine) as session:
        p = MarketProfile(
            id="oil",
            name="Oil Markets",
            regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
        )
        session.add(p)
        session.commit()
        session.refresh(p)
    assert p.regime_labels == ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]


def test_connector_type_values():
    assert ConnectorType.BUILTIN == "builtin"
    assert ConnectorType.SPEC == "spec"
    assert ConnectorType.GENERATED == "generated"


def test_connector_defaults(engine):
    with Session(engine) as session:
        c = Connector(id="yfinance", name="yfinance")
        session.add(c)
        session.commit()
        session.refresh(c)
    assert c.type == ConnectorType.BUILTIN
    assert c.is_active is True
    assert c.code is None
