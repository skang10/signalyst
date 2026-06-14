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
from src.db.models import DataArtifact, SessionStage, SessionStatus, UploadedSource
from src.db.models import Session as SessionModel
from src.services.hashing import stable_hash

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
        await _run(s, db)


def _uploaded_source_to_series(uploaded: UploadedSource) -> dict[str, pd.Series]:
    if uploaded.raw_data is not None:
        return {
            col: pd.Series(v["data"], index=pd.DatetimeIndex(v["index"]), name=col, dtype=float)
            for col, v in uploaded.raw_data.items()
        }
    if uploaded.raw_data_ref:
        df = pd.read_parquet(uploaded.raw_data_ref)
        return {col: df[col].rename(col) for col in df.columns}
    return {}


def _raw_data_to_series(raw_data: dict[str, Any]) -> dict[str, pd.Series]:
    return {
        col: pd.Series(v["data"], index=pd.DatetimeIndex(v["index"]), name=col, dtype=float)
        for col, v in raw_data.items()
    }


def _load_artifact_raw_data(artifact: DataArtifact) -> dict[str, Any]:
    if artifact.raw_data is not None:
        return artifact.raw_data
    if artifact.raw_data_ref:
        df = pd.read_parquet(artifact.raw_data_ref)
        return {
            col: {
                "index": [str(idx.date()) for idx in df.index],
                "data": [None if pd.isna(v) else float(v) for v in df[col]],
            }
            for col in df.columns
        }
    return {}


def _expected_signal_keys(connector_pending: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for p in connector_pending:
        cid = p.get("connector_id")
        params = p.get("params", {})
        if cid == "yfinance":
            keys.update(params.get("tickers", []))
        elif cid == "fred":
            keys.update(params.get("series_ids", []))
        elif cid == "eia":
            keys.add("eia_inventory_change")
        elif cid == "gpr":
            keys.add("GPR")
    return keys


def _diff_sources(
    connector_pending: list[dict[str, Any]], prev_sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only the connector_pending entries that aren't already covered by
    prev_sources, so a chat-triggered refetch only fetches newly-added sources."""
    prev_by_id = {p.get("connector_id"): p for p in prev_sources}
    to_fetch: list[dict[str, Any]] = []
    for p in connector_pending:
        cid = p.get("connector_id")
        params = p.get("params", {})
        prev = prev_by_id.get(cid)
        if cid == "yfinance":
            prev_tickers = set(prev.get("params", {}).get("tickers", [])) if prev else set()
            new_tickers = [t for t in params.get("tickers", []) if t not in prev_tickers]
            if new_tickers:
                to_fetch.append({"connector_id": cid, "params": {"tickers": new_tickers}})
        elif cid == "fred":
            prev_series = set(prev.get("params", {}).get("series_ids", [])) if prev else set()
            new_series = [s for s in params.get("series_ids", []) if s not in prev_series]
            if new_series:
                to_fetch.append({"connector_id": cid, "params": {"series_ids": new_series}})
        elif cid in ("eia", "gpr"):
            if prev is None:
                to_fetch.append(p)
        else:
            to_fetch.append(p)
    return to_fetch


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


async def _finish_stage(
    s: SessionModel,
    db: AsyncSession,
    session_id_str: str,
    is_auto: bool,
    current_activity_events: list[Any],
    current_stage_history: list[Any],
    current_conversation: list[Any],
    data_manifest: dict[str, Any],
    artifact_event: dict[str, Any],
    extra_events: list[dict[str, Any]] | None = None,
) -> None:
    """Commit session state update and greeting after data is ready (fresh or cached)."""
    now_str = artifact_event["created_at"]
    now = datetime.fromisoformat(now_str).replace(tzinfo=None)

    if is_auto:
        next_stage = SessionStage.FEATURIZING
        next_status = SessionStatus.RUNNING
    else:
        next_stage = SessionStage.USER_REVIEW
        next_status = SessionStatus.WAITING

    new_stage_entry = {"stage": next_stage.value, "entered_at": now_str}
    events = [*(extra_events or []), artifact_event]

    s.activity_events = [*current_activity_events, *events]
    s.stage = next_stage.value
    s.stage_history = [*current_stage_history, new_stage_entry]
    s.status = next_status.value
    s.updated_at = now

    if not is_auto:
        tickers = data_manifest.get("tickers", [])
        rows = data_manifest.get("rows", 0)
        dr = data_manifest.get("date_range", {})
        missing = data_manifest.get("missing_pct", {})
        ticker_str = ", ".join(tickers[:4])
        if len(tickers) > 4:
            ticker_str += f" +{len(tickers) - 4} more"
        date_str = (
            f" from {dr['start']} to {dr['end']}" if dr.get("start") and dr.get("end") else ""
        )
        high_missing = [k for k, v in missing.items() if v > 10]
        warning = f" ⚠ High missing data: {', '.join(high_missing)}." if high_missing else ""
        greeting = (
            f"I've collected {rows} rows across {len(tickers)} signal"
            f"{'s' if len(tickers) != 1 else ''} ({ticker_str}){date_str}.{warning} "
            f"Check the Data tab to review the snapshot. "
            f'Say "run analysis" to proceed, or ask me to add or adjust data sources.'
        )
        already_greeted = any(
            m.get("role") == "assistant" and m.get("content") == greeting
            for m in current_conversation
        )
        if already_greeted:
            s.conversation = current_conversation
        else:
            s.conversation = [
                *current_conversation,
                {"role": "assistant", "content": greeting, "created_at": now_str},
            ]

    await db.commit()
    log.info("data_agent.stage_advanced", session_id=session_id_str, stage=next_stage.value)


async def _run(s: SessionModel, db: AsyncSession) -> None:
    # Snapshot everything before the first await — asyncpg expires the object
    # when the connection returns to the pool between async calls.
    session_id = s.id
    session_id_str = str(session_id)
    current_activity_events = list(s.activity_events or [])
    current_stage_history = list(s.stage_history or [])
    current_conversation = list(s.conversation or [])
    is_auto = s.auto

    pending = list(s.pending_sources or [])
    connector_pending = [p for p in pending if p.get("connector_id") != "upload"]
    upload_pending = [p for p in pending if p.get("connector_id") == "upload"]
    requested_start = str(s.timeframe_start) if s.timeframe_start else ""
    requested_end = str(s.timeframe_end) if s.timeframe_end else ""
    log.info(
        "data_agent.starting",
        session_id=session_id_str,
        n_pending_sources=len(pending),
        sources=[p.get("connector_id") for p in pending],
    )

    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{session_id_str}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        # Load uploaded source data referenced by pending_sources — these are merged into
        # the freshly-fetched connector signals below, and their identity feeds the cache
        # hash so a change in which uploads are included invalidates the cache.
        prev_artifact_result = await db.execute(
            select(DataArtifact)
            .where(DataArtifact.session_id == session_id)
            .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        prev_artifact = prev_artifact_result.scalar_one_or_none()

        uploaded_sources: list[UploadedSource] = []
        for up in upload_pending:
            row = await db.execute(
                select(UploadedSource)
                .where(
                    UploadedSource.session_id == session_id,
                    UploadedSource.source_name == up.get("source_name"),
                )
                .order_by(UploadedSource.created_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            )
            uploaded = row.scalars().first()
            if uploaded is not None:
                uploaded_sources.append(uploaded)

        source_str = json.dumps(
            sorted(connector_pending, key=lambda x: x.get("connector_id", "")), sort_keys=True
        )
        upload_ids_str = json.dumps(sorted(str(u.id) for u in uploaded_sources))
        source_hash = stable_hash(
            hashlib.sha256(source_str.encode()).hexdigest(),
            upload_ids_str,
            requested_start,
            requested_end,
        )

        # --- Cache lookup ---
        cached_result = await db.execute(
            select(DataArtifact)
            .where(DataArtifact.source_hash == source_hash)
            .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        cached = cached_result.scalar_one_or_none()

        if cached is not None:
            log.info(
                "data_agent.cache_hit",
                session_id=session_id_str,
                cached_artifact=str(cached.id),
            )
            artifact_id = uuid.uuid4()
            count_result = await db.execute(
                select(func.count()).where(DataArtifact.session_id == session_id)
            )
            round_num = (count_result.scalar() or 0) + 1
            data_manifest = {
                **cached.data_manifest,
                "requested_start": requested_start,
                "requested_end": requested_end,
            }

            a = DataArtifact(
                id=artifact_id,
                session_id=session_id,
                round=round_num,
                sources=cached.sources,
                data_manifest=data_manifest,
                raw_data=cached.raw_data,
                raw_data_ref=cached.raw_data_ref,
                source_hash=source_hash,
                cached_from_session_id=cached.session_id,
                cached_from_artifact_id=cached.id,
                cache_hit=True,
            )
            db.add(a)

            now = datetime.now(UTC)
            cache_event: dict[str, Any] = {
                "event_id": str(uuid.uuid4()),
                "created_at": now.isoformat(),
                "type": "cache_hit",
                "artifact_id": str(artifact_id),
                "cached_from_artifact_id": str(cached.id),
                "cached_from_created_at": cached.created_at.replace(tzinfo=UTC).isoformat(),
            }
            artifact_event: dict[str, Any] = {
                "event_id": str(uuid.uuid4()),
                "created_at": now.isoformat(),
                "type": "artifact_ready",
                "kind": "data",
                "artifact_id": str(artifact_id),
                "rows": data_manifest["rows"],
                "tickers": data_manifest["tickers"],
            }
            await _finish_stage(
                s,
                db,
                session_id_str,
                is_auto,
                current_activity_events,
                current_stage_history,
                current_conversation,
                data_manifest,
                artifact_event,
                extra_events=[cache_event],
            )
            await publisher(cache_event)
            await publisher(artifact_event)
            log.info("data_agent.cache_hit_complete", session_id=session_id_str, round=round_num)
            return

        # --- No cache hit: run the agent ---
        ctx = AgentContext(
            date_range_start=str(s.timeframe_start),
            date_range_end=str(s.timeframe_end),
        )
        # If a previous artifact exists for this session, only fetch sources that
        # weren't already covered by it — a chat-triggered refetch should only hit
        # the newly-added tickers/series, not re-fetch everything.
        diffing = prev_artifact is not None and bool(connector_pending)
        to_fetch = connector_pending
        carried_signals: dict[str, pd.Series] = {}
        if diffing and prev_artifact is not None:
            to_fetch = _diff_sources(connector_pending, prev_artifact.sources or [])
            expected_keys = _expected_signal_keys(connector_pending)
            prev_series = _raw_data_to_series(_load_artifact_raw_data(prev_artifact))
            carried_signals = {k: v for k, v in prev_series.items() if k in expected_keys}

        if diffing and not to_fetch:
            pass  # nothing new to fetch — skip the agent entirely
        else:
            if diffing:
                initial_msg = f"Fetch the following NEW data sources only: {json.dumps(to_fetch)}"
            elif connector_pending:
                initial_msg = (
                    f"Fetch the following approved data sources: {json.dumps(connector_pending)}"
                )
            elif pending:
                initial_msg = "No connector data sources requested for this run."
            else:
                initial_msg = (
                    "Fetch the default oil data sources: yfinance (CL=F, BZ=F, DX-Y.NYB),"
                    " fred (INDPRO), eia, gpr."
                )
            agent = make_data_agent()
            await agent.run(context=ctx, publisher=publisher, initial_user_message=initial_msg)

        for key, series in carried_signals.items():
            ctx.signals.setdefault(key, series)

        # Merge in previously uploaded sources still listed in pending_sources — these
        # aren't re-fetched by the agent, just re-attached to the fresh result.
        for uploaded in uploaded_sources:
            for col, series in _uploaded_source_to_series(uploaded).items():
                ctx.signals[col] = series

        # All reads below use snapshots — s is expired after the await above
        raw_data = _series_to_raw_data(ctx.signals)
        data_manifest = {
            **_build_manifest(ctx.signals),
            "requested_start": requested_start,
            "requested_end": requested_end,
        }

        artifact_id = uuid.uuid4()
        count_result = await db.execute(
            select(func.count()).where(DataArtifact.session_id == session_id)
        )
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
            {"connector_id": p["connector_id"], "params": p.get("params", {})}
            for p in connector_pending
        ] + upload_pending
        a = DataArtifact(
            id=artifact_id,
            session_id=session_id,
            round=round_num,
            sources=sources,
            data_manifest=data_manifest,
            raw_data=raw_data_out,
            raw_data_ref=raw_data_ref,
            source_hash=source_hash,
        )
        db.add(a)

        now = datetime.now(UTC)
        artifact_event = {
            "event_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "type": "artifact_ready",
            "kind": "data",
            "artifact_id": str(artifact_id),
            "rows": data_manifest["rows"],
            "tickers": data_manifest["tickers"],
        }
        await _finish_stage(
            s,
            db,
            session_id_str,
            is_auto,
            current_activity_events,
            current_stage_history,
            current_conversation,
            data_manifest,
            artifact_event,
        )
        await publisher(artifact_event)
        log.info(
            "data_agent.complete",
            session_id=session_id_str,
            n_signals=len(ctx.signals),
            round=round_num,
        )
    except Exception as exc:
        log.error("data_agent.failed", session_id=session_id_str, error=str(exc))
        now = datetime.now(UTC)
        error_event: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "type": "error",
            "stage": "data_gathering",
            "message": str(exc),
        }
        s.status = SessionStatus.FAILED.value
        s.error = str(exc)
        s.updated_at = now.replace(tzinfo=None)
        s.activity_events = [*current_activity_events, error_event]
        await db.commit()
        await publisher(error_event)
    finally:
        await r.aclose()  # type: ignore[attr-defined]
