from __future__ import annotations

from src.agents.followup_agent import make_followup_agent


def test_make_followup_agent_registers_rerun_tools_as_stop_tools() -> None:
    agent = make_followup_agent()
    assert agent.name == "FollowUpAgent"
    assert set(agent._tools) == {"rerun_featurizer", "rerun_data_gathering"}
    assert agent._tools["rerun_featurizer"].is_stop is True
    assert agent._tools["rerun_data_gathering"].is_stop is True


def test_followup_agent_system_prompt_instructs_never_invent_and_reply() -> None:
    agent = make_followup_agent()
    prompt = agent.system_prompt.lower()
    assert "never invent" in prompt
    assert "reply" in prompt


def test_rerun_featurizer_tool_returns_rerun_intent_with_reply() -> None:
    agent = make_followup_agent()
    fn = agent._tools["rerun_featurizer"].fn
    result = fn(
        featurizer_config_patch={"windows": [60]},
        reply="Sure, switching to 60-day windows.",
        context=None,
    )
    assert result == {
        "action": "rerun",
        "stage": "featurizing",
        "patch": {"windows": [60]},
        "reply": "Sure, switching to 60-day windows.",
    }


def test_rerun_data_gathering_tool_returns_rerun_intent_with_reply() -> None:
    agent = make_followup_agent()
    fn = agent._tools["rerun_data_gathering"].fn
    result = fn(
        sources_to_add=["Brent crude futures"],
        reply="Adding Brent crude now.",
        context=None,
    )
    assert result == {
        "action": "rerun",
        "stage": "data_gathering",
        "sources_to_add": ["Brent crude futures"],
        "reply": "Adding Brent crude now.",
    }
