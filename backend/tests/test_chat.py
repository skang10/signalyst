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


def test_chat_advance_action_emits_stage_transition_activity_event(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {"action": "advance", "updates": {}, "reply": "Proceeding."}
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock),
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "run it"})

    detail = client.get(f"/api/sessions/{session_id}").json()
    transitions = [e for e in detail["activity_events"] if e["type"] == "stage_transition"]
    assert any(t["to"] == "featurizing" for t in transitions)


def test_chat_update_config_action_emits_stage_transition_activity_event(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {
        "action": "update_config",
        "updates": {"featurizer_config_patch": {"windows": [10, 30]}},
        "reply": "Updated windows and proceeding.",
    }
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock),
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(
            f"/api/sessions/{session_id}/chat",
            json={"message": "use 10 and 30 day windows"},
        )

    detail = client.get(f"/api/sessions/{session_id}").json()
    transitions = [e for e in detail["activity_events"] if e["type"] == "stage_transition"]
    assert any(t["to"] == "featurizing" for t in transitions)


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


def test_chat_answer_action_keeps_user_review_and_does_not_start_background_work(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {
        "action": "answer",
        "updates": {},
        "reply": "I can help review the fetched oil-market data before you run analysis.",
    }
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock) as mock_feat,
        patch("api.routes.chat._run_data_agent_background", new_callable=AsyncMock) as mock_data,
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        res = client.post(f"/api/sessions/{session_id}/chat", json={"message": "who are you?"})

    assert res.status_code == 202
    mock_feat.assert_not_called()
    mock_data.assert_not_called()

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["stage"] == "user_review"
    assert detail["status"] == "waiting"
    last = detail["conversation"][-1]
    assert last["role"] == "assistant"
    assert (
        last["content"] == "I can help review the fetched oil-market data before you run analysis."
    )


def test_chat_missing_action_defaults_to_answer_not_analysis(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {"updates": {}, "reply": "I can answer questions before analysis runs."}
    with (
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
        patch("api.routes.chat._run_featurizer_background", new_callable=AsyncMock) as mock_bg,
    ):
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        res = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hello"})

    assert res.status_code == 202
    mock_bg.assert_not_called()

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["stage"] == "user_review"
    assert detail["status"] == "waiting"


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


def test_review_interpreter_accepts_answer_action():
    import asyncio

    from src.agents.review_interpreter import ReviewInterpreter

    interp = ReviewInterpreter()

    async def fake_create(**kwargs):  # type: ignore[return]
        system_prompt = kwargs["messages"][0]["content"]
        assert '"answer"' in system_prompt
        assert "normal chatbot" in system_prompt
        msg = MagicMock()
        msg.content = json.dumps(
            {
                "action": "answer",
                "updates": {},
                "reply": "I can answer questions about this review step without running analysis.",
            }
        )
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    with patch("src.agents.review_interpreter.openai.AsyncOpenAI") as cls:
        cls.return_value.chat.completions.create = fake_create
        result = asyncio.run(
            interp.interpret(
                message="what can you do?",
                session_stage="user_review",
                conversation=[],
                data_manifest={"tickers": ["CL=F"]},
            )
        )

    assert result["action"] == "answer"


def test_review_interpreter_includes_conversation_history_in_prompt():
    import asyncio

    from src.agents.review_interpreter import ReviewInterpreter

    interp = ReviewInterpreter()
    captured: dict[str, str] = {}

    async def fake_create(**kwargs):  # type: ignore[return]
        captured["user_content"] = kwargs["messages"][1]["content"]
        msg = MagicMock()
        msg.content = json.dumps({"action": "answer", "updates": {}, "reply": "..."})
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    conversation = [
        {"role": "assistant", "content": "Tell me which parameter to change, or say 'proceed'."},
        {"role": "user", "content": "For example, which windows would you suggest?"},
    ]

    with patch("src.agents.review_interpreter.openai.AsyncOpenAI") as cls:
        cls.return_value.chat.completions.create = fake_create
        asyncio.run(
            interp.interpret(
                message="For example, which windows would you suggest?",
                session_stage="user_review",
                conversation=conversation,
                data_manifest={"tickers": ["CL=F"]},
            )
        )

    assert "Tell me which parameter to change" in captured["user_content"]


def test_review_interpreter_system_prompt_guards_against_question_misclassification():
    from src.agents.review_interpreter import _SYSTEM_PROMPT

    assert "question-form" in _SYSTEM_PROMPT.lower()
