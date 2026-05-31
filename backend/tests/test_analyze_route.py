from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from src.db.models import RunStatus
from src.db.session import get_session


def _make_mock_run(run_id: str = "00000000-0000-0000-0000-000000000001") -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.status = "pending"
    run.result = None
    return run


def test_trigger_analysis_returns_202_with_run_id() -> None:
    mock_run = _make_mock_run()

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()  # synchronous in SQLAlchemy
        mock_session.refresh = AsyncMock(return_value=None)
        mock_run.id = "00000000-0000-0000-0000-000000000001"
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop"):
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                    "tasks": ["regime_classification"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert "run_id" in response.json()


def test_trigger_analysis_defaults_to_quick_mode() -> None:
    mock_run = _make_mock_run()

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        mock_run.id = "00000000-0000-0000-0000-000000000001"
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                    "tasks": ["regime_classification"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.args[4] == "quick"


def test_trigger_analysis_accepts_full_mode() -> None:
    mock_run = _make_mock_run()

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        mock_run.id = "00000000-0000-0000-0000-000000000001"
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                    "tasks": ["regime_classification"],
                    "analysis_mode": "full",
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.args[4] == "full"


def test_get_run_returns_404_for_missing_run() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = None
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/runs/00000000-0000-0000-0000-000000000099")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404


def test_get_run_returns_422_for_invalid_uuid() -> None:
    client = TestClient(app)
    response = client.get("/api/runs/not-a-uuid")
    assert response.status_code == 422


def test_cancel_run_marks_run_canceled() -> None:
    mock_run = _make_mock_run()
    mock_run.status = "running"
    mock_run.error = None

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_run
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post("/api/runs/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert mock_run.status == "canceled"
    assert mock_run.error == "Canceled by user"


def test_cancel_run_returns_409_for_completed_run() -> None:
    mock_run = _make_mock_run()
    mock_run.status = "completed"

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_run
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post("/api/runs/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409


def test_trigger_analysis_forwards_pre_messages_to_loop() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                    "pre_messages": ["Add Baker Hughes rig count data"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.kwargs["pre_messages"] == ["Add Baker Hughes rig count data"]


def test_trigger_analysis_defaults_pre_messages_to_empty_list() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.kwargs["pre_messages"] == []


def _make_completed_run(
    run_id: str = "00000000-0000-0000-0000-000000000001",
) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.status = RunStatus.COMPLETED
    run.result = {
        "summary": "Range-bound regime detected.",
        "regime": {"regime": "range_bound", "confidence": 0.82},
        "direction": None,
        "drift": None,
        "feature_importance": None,
        "backtest": None,
    }
    run.date_range_start = "2023-01-01"
    run.date_range_end = "2023-06-30"
    run.tasks = ["regime_classification"]
    return run


def test_continue_run_returns_202_with_new_run_id() -> None:
    source_run = _make_completed_run()
    new_run = MagicMock()
    new_run.id = "00000000-0000-0000-0000-000000000002"
    call_count = 0

    async def override_session():  # type: ignore[return]
        nonlocal call_count
        mock_session = AsyncMock()
        if call_count == 0:
            mock_session.get.return_value = source_run
        else:
            mock_session.get.return_value = new_run
            mock_session.refresh = AsyncMock(return_value=None)
        call_count += 1
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_continuation"):
            client = TestClient(app)
            response = client.post(
                "/api/runs/00000000-0000-0000-0000-000000000001/continue",
                json={"message": "Why is drift elevated?"},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert "run_id" in response.json()


def test_continue_run_returns_404_for_missing_source_run() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = None
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs/00000000-0000-0000-0000-000000000099/continue",
            json={"message": "hello"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404


def test_continue_run_returns_409_if_source_not_completed() -> None:
    source_run = MagicMock()
    source_run.status = RunStatus.RUNNING

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = source_run
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs/00000000-0000-0000-0000-000000000001/continue",
            json={"message": "hello"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409


def test_continue_run_returns_422_for_invalid_run_id() -> None:
    client = TestClient(app)
    response = client.post("/api/runs/not-a-uuid/continue", json={"message": "hello"})
    assert response.status_code == 422
