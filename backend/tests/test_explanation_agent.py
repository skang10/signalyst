from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.agents.explanation_agent import make_explanation_agent


def _text_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _mock_client(responses: list) -> MagicMock:
    idx = {"v": 0}

    async def create(**kwargs):  # type: ignore[return]
        resp = responses[min(idx["v"], len(responses) - 1)]
        idx["v"] += 1
        return resp

    c = MagicMock()
    c.chat.completions.create = create
    return c


def test_make_explanation_agent_has_no_tools() -> None:
    agent = make_explanation_agent()
    assert agent.name == "ExplanationAgent"
    assert agent._tools == {}


def test_explanation_agent_prompt_specifies_sections_and_disclaimer() -> None:
    agent = make_explanation_agent()
    prompt = agent.system_prompt
    assert "## Suggestion" in prompt
    assert "## Analysis & Evidence" in prompt
    assert "Not financial advice" in prompt


@pytest.mark.asyncio
async def test_explanation_agent_returns_text_and_streams_thought() -> None:
    agent = make_explanation_agent()
    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client(
            [_text_resp("The model calls a bull_supercycle regime with 80% confidence.")]
        )
        result = await agent.run(
            context=None, publisher=pub, initial_user_message="Summarize this analysis."
        )

    assert result == "The model calls a bull_supercycle regime with 80% confidence."
    assert any(e["type"] == "thought" and e["agent"] == "ExplanationAgent" for e in events)
