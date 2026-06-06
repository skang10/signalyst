from __future__ import annotations

import json
from typing import Any

import openai

from src.config import settings

_SYSTEM_PROMPT = """\
You are ReviewInterpreter. Classify the user's intent at the data review stage.

Given the user's message and session context, output a JSON object with:
- "action": one of "advance" | "refetch" | "update_config" | "answer"
- "updates": object with optional keys:
    - "sources_to_add": list of connector IDs to add (for "refetch")
    - "featurizer_config_patch": dict of config overrides (for "update_config")
- "reply": a short natural-language reply to show the user

Rules:
- "advance": user wants to proceed to featurizing (e.g. "looks good", "run it", "proceed")
- "refetch": user wants to add/change data sources (e.g. "add X", "fetch Y too")
- "update_config": user wants to change featurizer settings (e.g. "use 30d windows")
- "answer": user asks a normal chatbot question, asks for context, or says something unrelated
  to running/refetching/configuring analysis

For "answer", respond like a normal chatbot with brief context about Signalyst and the current
USER_REVIEW step. Do not claim analysis is running unless the user explicitly asks to proceed.

Respond ONLY with the JSON object. No other text.
"""


class ReviewInterpreter:
    async def interpret(
        self,
        message: str,
        session_stage: str,
        conversation: list[dict[str, Any]],
        data_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        user_content = (
            f"Session stage: {session_stage}\n"
            f"Data manifest tickers: {data_manifest.get('tickers', [])}\n"
            f"User message: {message}"
        )
        resp = await client.chat.completions.create(
            model=settings.agent_model_fast,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)  # type: ignore[no-any-return]
