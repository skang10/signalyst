import pytest
from pydantic import ValidationError

from api.models import RunResult, RunStatus


def test_run_status_values():
    assert RunStatus.PENDING == "pending"
    assert RunStatus.RUNNING == "running"
    assert RunStatus.COMPLETED == "completed"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.CANCELED == "canceled"


def test_run_result_valid():
    r = RunResult(run_id="abc", status=RunStatus.PENDING)
    assert r.status == RunStatus.PENDING
    assert r.result is None


def test_run_result_rejects_invalid_status():
    with pytest.raises(ValidationError):
        RunResult(run_id="abc", status="unknown")  # type: ignore[arg-type]


def test_run_result_serializes_status_as_string():
    r = RunResult(run_id="abc", status=RunStatus.COMPLETED)
    assert r.model_dump()["status"] == "completed"
