from __future__ import annotations

import hashlib
import json
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import func, select

from src.agent.tools import AgentContext
from src.agents.data_agent import make_data_agent
from src.config import settings
from src.db.models import DataArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.hashing import stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()
_ARTIFACTS_DIR = pathlib.Path("data/artifacts")
_RAW_INLINE_THRESHOLD = 5 * 1024 * 1024


async def run_data_agent_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("data_agent.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            return
        if s.stage != SessionStage.DATA_GATHERING:
            log.info("data_agent.wrong_stage", session_id=str(session_id), stage=s.stage)
            return
        try:
            await _run(s, db)
        except Exception as exc:
            log.error("data_agent.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(
                s, {"type": "error", "stage": "data_gathering", "message": str(exc)}
            )
            await db.commit()


def _series_to_raw_data(signals: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, series in signals.items():
        if isinstance(series, pd.Series):
            result[key] = {
                "index": [
                    str(idx.date()) if hasattr(idx, "date") else str(idx) for idx in series.index
                ],
                "data": [None if pd.isna(v) else float(v) for v in series.values],
            }
    return result


def _build_manifest(signals: dict[str, Any]) -> dict[str, Any]:
    tickers = [k for k, v in signals.items() if isinstance(v, pd.Series)]
    if not tickers:
        return {"tickers": [], "rows": 0, "date_range": {}, "missing_pct": {}, "summary_stats": {}}
    first = next(v for v in signals.values() if isinstance(v, pd.Series))
    rows = len(first)
    date_range = {
        "start": str(first.index.min().date()) if rows else "",
        "end": str(first.index.max().date()) if rows else "",
    }
    missing_pct = {
        k: round(float(v.isna().mean() * 100), 2)
        for k, v in signals.items()
        if isinstance(v, pd.Series)
    }
    summary_stats = {
        k: {
            "mean": round(float(v.mean(skipna=True)), 4),
            "std": round(float(v.std(skipna=True)), 4),
            "min": round(float(v.min(skipna=True)), 4),
            "max": round(float(v.max(skipna=True)), 4),
        }
        for k, v in signals.items()
        if isinstance(v, pd.Series)
    }
    return {
        "tickers": tickers,
        "rows": rows,
        "date_range": date_range,
        "missing_pct": missing_pct,
        "summary_stats": summary_stats,
    }


async def _run(s: SessionModel, db: AsyncSession) -> None:
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{s.id}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        pending = list(s.pending_sources or [])
        log.info(
            "data_agent.starting",
            session_id=str(s.id),
            n_pending_sources=len(pending),
            sources=[p.get("connector_id") for p in pending],
        )
        ctx = AgentContext(
            date_range_start=str(s.timeframe_start),
            date_range_end=str(s.timeframe_end),
        )
        initial_msg = (
            f"Fetch the following approved data sources: {json.dumps(pending)}"
            if pending
            else (
                "Fetch the default oil data sources: yfinance (CL=F, BZ=F, DX-Y.NYB),"
                " fred (INDPRO), eia, gpr."
            )
        )
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=publisher, initial_user_message=initial_msg)

        raw_data = _series_to_raw_data(ctx.signals)
        data_manifest = _build_manifest(ctx.signals)

        source_str = json.dumps(
            sorted(pending, key=lambda x: x.get("connector_id", "")), sort_keys=True
        )
        source_hash = stable_hash(hashlib.sha256(source_str.encode()).hexdigest())

        artifact_id = uuid.uuid4()
        count_result = await db.execute(select(func.count()).where(DataArtifact.session_id == s.id))
        round_num = (count_result.scalar() or 0) + 1

        raw_json = json.dumps(raw_data).encode()
        if len(raw_json) <= _RAW_INLINE_THRESHOLD:
            raw_data_out: dict[str, Any] | None = raw_data
            raw_data_ref: str | None = None
        else:
            _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            ref = str(_ARTIFACTS_DIR / f"{artifact_id}.parquet")
            df = pd.DataFrame(
                {
                    k: pd.Series(v["data"], index=pd.DatetimeIndex(v["index"]))
                    for k, v in raw_data.items()
                }
            )
            df.to_parquet(ref)
            raw_data_out = None
            raw_data_ref = ref

        sources = [
            {"connector_id": p["connector_id"], "params": p.get("params", {})} for p in pending
        ]
        a = DataArtifact(
            id=artifact_id,
            session_id=s.id,
            round=round_num,
            sources=sources,
            data_manifest=data_manifest,
            raw_data=raw_data_out,
            raw_data_ref=raw_data_ref,
            source_hash=source_hash,
        )
        db.add(a)

        s.pending_sources = []
        append_activity_event(
            s,
            {
                "type": "artifact_ready",
                "kind": "data",
                "artifact_id": str(artifact_id),
                "rows": data_manifest["rows"],
                "tickers": data_manifest["tickers"],
            },
        )

        if s.auto:
            transition_stage(s, SessionStage.FEATURIZING)
            set_status(s, SessionStatus.RUNNING)
        else:
            transition_stage(s, SessionStage.USER_REVIEW)
            set_status(s, SessionStatus.WAITING)

        await db.commit()
        log.info(
            "data_agent.complete",
            session_id=str(s.id),
            n_signals=len(ctx.signals),
            round=round_num,
        )
    finally:
        await r.aclose()  # type: ignore[attr-defined]
