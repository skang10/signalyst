from __future__ import annotations

from typing import Any

from src.agent.tools import AgentContext
from src.agents.base import BaseAgent

_SYSTEM_PROMPT = """\
You are FollowUpAgent. The user is looking at a completed market regime analysis and may ask \
follow-up questions or ask you to change settings and re-run.

You will be given, in the user message:
- The regime classification result (regime label + confidence) and the price-direction \
prediction (direction + confidence)
- Drift-detection findings (whether drift was detected, drifted features, PSI score)
- Feature-importance (SHAP) and backtest results — these may be present or may be null/missing
- The data sources used (data manifest) and the featurizer settings (featurizer_config)
- A comparable prior session for this market profile, if one exists \
({"available": true, "regime": ..., "direction": ..., "summary": ..., "timeframe": ...} \
or {"available": false})
- Recent conversation turns

For questions about the regime, direction, drift, data sources, featurizer settings, or how \
this session compares to the prior one, answer directly and tersely from the information above \
— do not call a tool for these.

IMPORTANT: Only discuss feature-importance (SHAP) or backtest results if they are explicitly \
present and non-null in the input, and only discuss the comparable session if its `available` \
field is true. If something is missing, say so plainly — never invent or speculate about data \
you were not given.

If — and only if — the user clearly asks you to change featurizer settings (e.g. window sizes, \
lags, feature families) or to add new data sources and re-run the analysis, call the matching \
tool:
- rerun_featurizer: patch featurizer_config and re-run from featurizing
- rerun_data_gathering: add data sources and re-run the full pipeline from data gathering

Both tools require a `reply` argument: a short, friendly natural-language confirmation of what \
you're about to do. This `reply` is the ONLY text the user will see for this turn, so always \
include one when calling either tool.

When answering directly, respond with plain text only — no JSON, no markdown headers.
"""


def make_followup_agent() -> BaseAgent:
    agent = BaseAgent(name="FollowUpAgent", system_prompt=_SYSTEM_PROMPT)

    def rerun_featurizer(
        featurizer_config_patch: dict[str, Any],
        reply: str,
        context: AgentContext | None = None,
    ) -> dict[str, Any]:
        """Patch the featurizer config and re-run featurizing (and downstream analysis)."""
        return {
            "action": "rerun",
            "stage": "featurizing",
            "patch": featurizer_config_patch,
            "reply": reply,
        }

    def rerun_data_gathering(
        sources_to_add: list[str],
        reply: str,
        context: AgentContext | None = None,
    ) -> dict[str, Any]:
        """Add data sources and re-run the full pipeline from data gathering."""
        return {
            "action": "rerun",
            "stage": "data_gathering",
            "sources_to_add": sources_to_add,
            "reply": reply,
        }

    agent.register_tool(
        rerun_featurizer,
        {
            "type": "object",
            "properties": {
                "featurizer_config_patch": {
                    "type": "object",
                    "description": (
                        'Partial featurizer_config to merge in, e.g. {"windows": [5, 30, 90]}'
                    ),
                },
                "reply": {
                    "type": "string",
                    "description": (
                        "Short natural-language confirmation of what you're about to do"
                    ),
                },
            },
            "required": ["featurizer_config_patch", "reply"],
        },
        is_stop=True,
    )
    agent.register_tool(
        rerun_data_gathering,
        {
            "type": "object",
            "properties": {
                "sources_to_add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Natural-language descriptions of data sources to add, "
                        'e.g. "Brent crude futures"'
                    ),
                },
                "reply": {
                    "type": "string",
                    "description": (
                        "Short natural-language confirmation of what you're about to do"
                    ),
                },
            },
            "required": ["sources_to_add", "reply"],
        },
        is_stop=True,
    )
    return agent
