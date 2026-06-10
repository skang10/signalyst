from __future__ import annotations

import json
import time
from typing import Any

import openai
import structlog

from src.config import settings

log = structlog.get_logger()

_SYSTEM_PROMPT = """\
You are ReviewInterpreter. Classify the user's intent at the data review stage.

Given the user's message and session context, output a JSON object with:
- "action": one of "advance" | "refetch" | "update_config" | "answer"
- "updates": object with optional keys:
    - "sources_to_add": list of connector IDs to add (for "refetch")
    - "featurizer_config_patch": dict of config overrides (for "update_config"). Use ONLY
      these exact keys — never invent alternatives like "rolling_windows_days" or
      "window_sizes":
        - "windows": list[int] of rolling-window day-counts, e.g. [7, 30, 90]
        - "lags": list[int] of lag day-counts, e.g. [1, 5, 20]
        - "feature_families": list[str] of feature family names
          (rolling_stats, momentum, regime, lag)
        - "energy_specific": bool
- "reply": a short natural-language reply to show the user

Rules:
- "advance": user gives an explicit instruction to proceed to featurizing (e.g. "looks good",
  "run it", "proceed", "go ahead")
- "refetch": user gives an explicit instruction to add/change data sources (e.g. "add X",
  "fetch Y too")
- "update_config": user gives an explicit instruction to change featurizer settings
  (e.g. "use 30d windows", "switch to lags of 1 and 5")
- "answer": user asks a normal chatbot question, asks for context or clarification, or says
  something unrelated to running/refetching/configuring analysis

Question-form messages — containing "?" or starting with words like "would", "could", "what",
"which", "how", "why", "can you" — that ask about settings, options, or process must be
classified as "answer", even if they mention configuration terms like "windows" or "lags".
Only classify as "advance"/"refetch"/"update_config" when the user gives an explicit
instruction, not when they are merely asking what you would suggest or how something works.

For "answer", respond like a normal chatbot with brief context about Signalyst and the current
USER_REVIEW step. Do not claim analysis is running unless the user explicitly asks to proceed.
When describing the current config use plain language, e.g. "Windows: 5, 20, 60 days · Lags: 1,
5, 20 days · Families: Rolling Stats, Momentum, Lag, Regime". Never echo raw field names like
"feature_families" or "rolling_stats" — translate them: rolling_stats→Rolling Stats,
momentum→Momentum, lag→Lag, regime→Regime.

For "update_config", the session stays in USER_REVIEW — changing a setting never starts the
pipeline by itself. Phrase the reply as a confirmation of the new setting plus a reminder that
the user can keep adjusting or say "run analysis"/"proceed" to start (e.g. "Updated to 30/90/180
day windows. Say 'run analysis' when ready, or keep adjusting."). Never say you are running or
about to run analysis for an "update_config" reply.

Respond ONLY with the JSON object. No other text.
"""

_FAMILY_LABELS = {
    "rolling_stats": "Rolling Stats",
    "momentum": "Momentum",
    "lag": "Lag",
    "regime": "Regime",
}


class ReviewInterpreter:
    async def interpret(
        self,
        message: str,
        session_stage: str,
        conversation: list[dict[str, Any]],
        data_manifest: dict[str, Any],
        featurizer_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        # `conversation` includes the current message as its last turn — use the
        # turns before it as context so the classifier knows what's being followed up on.
        prior_turns = conversation[:-1][-6:]
        history = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in prior_turns)
        history_block = f"Recent conversation:\n{history}\n" if history else ""
        cfg_block = ""
        if featurizer_config:
            families = [
                _FAMILY_LABELS.get(f, f) for f in featurizer_config.get("feature_families", [])
            ]
            cfg_block = (
                f"Current featurizer config: "
                f"windows={featurizer_config.get('windows', [])} days, "
                f"lags={featurizer_config.get('lags', [])} days, "
                f"families=[{', '.join(families)}], "
                f"energy_specific={featurizer_config.get('energy_specific', False)}\n"
            )
        user_content = (
            f"Session stage: {session_stage}\n"
            f"Data manifest tickers: {data_manifest.get('tickers', [])}\n"
            f"{cfg_block}"
            f"{history_block}"
            f"User message: {message}"
        )
        log.debug(
            "review_interpreter.request",
            model=settings.agent_model_fast,
            user_content_len=len(user_content),
            prior_turns=len(prior_turns),
        )
        start = time.monotonic()
        resp = await client.chat.completions.create(
            model=settings.agent_model_fast,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        log.info(
            "review_interpreter.response",
            model=settings.agent_model_fast,
            duration_ms=round((time.monotonic() - start) * 1000, 2),
            usage=resp.usage.model_dump() if resp.usage else None,
            content=content,
        )
        return json.loads(content)  # type: ignore[no-any-return]
