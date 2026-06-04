from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd


def _make_csv_bytes(n: int = 100) -> bytes:
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], "CL=F": range(n)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _setup_session_at_user_review(client) -> str:
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        session_id = client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2023-01-01",
                "timeframe_end": "2023-06-30",
            },
        ).json()["session_id"]

    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    return session_id


def test_chat_at_user_review_returns_202(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {"action": "advance", "updates": {}, "reply": "Running analysis now."}
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock),
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        res = client.post(
            f"/api/sessions/{session_id}/chat",
            json={"message": "looks good, proceed"},
        )
    assert res.status_code == 202


def test_chat_at_wrong_stage_returns_409(client):
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        session_id = client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2023-01-01",
                "timeframe_end": "2023-06-30",
            },
        ).json()["session_id"]

    res = client.post(
        f"/api/sessions/{session_id}/chat",
        json={"message": "hello"},
    )
    assert res.status_code == 409


def test_chat_advance_action_triggers_featurizing(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {"action": "advance", "updates": {}, "reply": "Proceeding."}
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock) as mock_bg,
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "run it"})

    mock_bg.assert_called_once()


def test_chat_refetch_action_triggers_data_gathering(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {
        "action": "refetch",
        "updates": {"sources_to_add": ["baker_hughes"]},
        "reply": "Refetching.",
    }
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_data_agent_background", new_callable=AsyncMock) as mock_bg,
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "add baker hughes"})

    mock_bg.assert_called_once()


def test_review_interpreter_classify_advance():
    import asyncio

    from src.agents.review_interpreter import ReviewInterpreter

    interp = ReviewInterpreter()

    async def fake_create(**kwargs):  # type: ignore[return]
        msg = MagicMock()
        msg.content = json.dumps({"action": "advance", "updates": {}, "reply": "Running."})
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    with patch("src.agents.review_interpreter.openai.AsyncOpenAI") as cls:
        cls.return_value.chat.completions.create = fake_create
        result = asyncio.run(
            interp.interpret(
                message="looks good proceed",
                session_stage="user_review",
                conversation=[],
                data_manifest={"tickers": ["CL=F"]},
            )
        )

    assert result["action"] == "advance"
