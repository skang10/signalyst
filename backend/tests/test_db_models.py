import uuid
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.db.models import Run, RunStatus


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


def test_run_default_status_is_pending(engine):
    with Session(engine) as session:
        run = Run(date_range_start="2024-01-01", date_range_end="2024-12-31")
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.status == RunStatus.PENDING


def test_run_id_is_uuid(engine):
    with Session(engine) as session:
        run = Run(date_range_start="2024-01-01", date_range_end="2024-12-31")
        session.add(run)
        session.commit()
        session.refresh(run)
    assert isinstance(run.id, uuid.UUID)


def test_run_created_at_is_set(engine):
    before = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        run = Run(date_range_start="2024-01-01", date_range_end="2024-12-31")
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.created_at >= before


def test_run_tasks_default_empty(engine):
    with Session(engine) as session:
        run = Run(date_range_start="2024-01-01", date_range_end="2024-12-31")
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.tasks == []


def test_run_stores_tasks(engine):
    tasks = ["regime_classification", "price_direction"]
    with Session(engine) as session:
        run = Run(
            date_range_start="2024-01-01",
            date_range_end="2024-12-31",
            tasks=tasks,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.tasks == tasks


def test_run_stores_result(engine):
    result = {"regime": "range_bound", "confidence": 0.82}
    with Session(engine) as session:
        run = Run(
            date_range_start="2024-01-01",
            date_range_end="2024-12-31",
            status=RunStatus.COMPLETED,
            result=result,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.result == result


def test_run_error_field(engine):
    with Session(engine) as session:
        run = Run(
            date_range_start="2024-01-01",
            date_range_end="2024-12-31",
            status=RunStatus.FAILED,
            error="FRED_API_KEY not set",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
    assert run.error == "FRED_API_KEY not set"


def test_run_status_values():
    assert RunStatus.PENDING == "pending"
    assert RunStatus.RUNNING == "running"
    assert RunStatus.COMPLETED == "completed"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.CANCELED == "canceled"
