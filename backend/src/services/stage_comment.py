from __future__ import annotations

from typing import Any

import openai
import structlog

from src.config import settings

log = structlog.get_logger()

_SYSTEM = (
    "You are a concise financial analysis assistant embedded in a trading dashboard. "
    "Write a single short paragraph (2-3 sentences, max 60 words) in first person "
    "summarising what just happened in the pipeline stage the user is looking at. "
    "Be specific — include actual numbers and labels. "
    "End with a concrete navigation hint (which tab to open). "
    "Do not use markdown, bullet points, or headers. Plain prose only."
)


async def generate_stage_comment(context: dict[str, Any]) -> str | None:
    """Generate a short conversational comment for a completed pipeline stage."""
    if not settings.openai_api_key:
        return None
    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=15.0)
        resp = await client.chat.completions.create(
            model=settings.agent_model_fast,
            max_tokens=100,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _format_context(context)},
            ],
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception as exc:
        log.warning("stage_comment.failed", error=str(exc))
        return None


def _format_context(ctx: dict[str, Any]) -> str:
    stage = ctx.get("stage", "")
    if stage == "featurizing":
        families = ", ".join(ctx.get("feature_families", [])) or "various transforms"
        return (
            f"Stage: feature engineering just completed. "
            f"Result: {ctx['n_features']} features built from {ctx['n_rows']} rows "
            f"using {families}. "
            f"Navigation hint: Features tab."
        )
    if stage == "analyzing":
        regime = (ctx.get("regime") or "unknown").replace("_", " ")
        conf = ctx.get("regime_confidence")
        conf_str = f" ({round(conf * 100)}% confidence)" if conf else ""
        direction = ctx.get("direction")
        dir_conf = ctx.get("direction_confidence")
        dir_str = ""
        if direction:
            dir_pct = f" ({round(dir_conf * 100)}%)" if dir_conf else ""
            dir_str = f" Direction bias: {direction}{dir_pct}."
        return (
            f"Stage: regime classification just completed. "
            f"Regime: {regime}{conf_str}.{dir_str} "
            f"Navigation hint: Overview tab for full breakdown."
        )
    if stage == "explaining":
        return (
            "Stage: market analysis summary just written. "
            "Navigation hint: Overview tab to read it."
        )
    return f"Stage {stage!r} just completed."
