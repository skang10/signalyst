from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.base import BaseAgent


def _text_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _tool_resp(name: str, args: dict, call_id: str = "c1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}
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


@pytest.mark.asyncio
async def test_base_agent_runs_tool_then_finishes() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    def echo(value: str, context: object = None) -> dict:
        """Echo a value."""
        return {"echoed": value}

    agent.register_tool(
        echo,
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
    )

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client([_tool_resp("echo", {"value": "hi"}), _text_resp("done")])
        result = await agent.run(context=None, publisher=pub)

    assert result == "done"
    assert any(e["type"] == "tool_call" and e["tool"] == "echo" for e in events)
    assert any(e["type"] == "tool_result" for e in events)


@pytest.mark.asyncio
async def test_base_agent_stop_tool_exits_loop() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    def approve(items: list, context: object = None) -> dict:
        """Approve items."""
        return {"approved": items}

    agent.register_tool(
        approve,
        {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "required": ["items"],
        },
        is_stop=True,
    )

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client(
            [
                _tool_resp("approve", {"items": ["a", "b"]}),
                _text_resp("should not reach"),
            ]
        )
        result = await agent.run(context=None, publisher=pub)

    data = json.loads(result)
    assert data["approved"] == ["a", "b"]
    assert len([e for e in events if e["type"] == "tool_call"]) == 1


@pytest.mark.asyncio
async def test_base_agent_thought_events_published() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        msg = MagicMock()
        msg.content = "thinking..."
        msg.tool_calls = None
        msg.model_dump.return_value = {}
        resp = MagicMock()
        resp.choices = [MagicMock(message=msg)]
        cls.return_value = _mock_client([resp])
        await agent.run(context=None, publisher=pub)

    assert any(e["type"] == "thought" and e["content"] == "thinking..." for e in events)


@pytest.mark.asyncio
async def test_base_agent_initial_user_message_prepended() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    captured: list[list] = []

    async def create(**kwargs):  # type: ignore[return]
        captured.append(kwargs["messages"])
        msg = MagicMock()
        msg.content = "ok"
        msg.tool_calls = None
        msg.model_dump.return_value = {}
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    c = MagicMock()
    c.chat.completions.create = create

    async def pub(e: dict) -> None:
        pass

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = c
        await agent.run(context=None, publisher=pub, initial_user_message="fetch oil data")

    first_call_msgs = captured[0]
    roles = [m["role"] for m in first_call_msgs]
    assert roles == ["system", "user"]
    assert first_call_msgs[1]["content"] == "fetch oil data"
