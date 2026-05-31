# Chat Window PR 2 — Post-Run Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a run completes, let the user send a follow-up message in the chat panel; the agent resumes with the previous result as context (decides whether to explain or use tools), and its summary appears as an agent bubble in the chat panel.

**Architecture:** `POST /api/runs/{run_id}/continue` creates a new run, passing the previous `Run.result` formatted as a context message plus the user's follow-up. A new `run_agent_continuation` function drives the same ReAct loop. The frontend introduces `continueToRun` (a store action that transitions to `running` without clearing `chatMessages`), wires the ChatPanel send button for the completed state, and adds example prompt chips. `AgentStream` detects the `done` event and adds the agent's summary to the chat panel when a continuation was in progress.

**Tech Stack:** FastAPI, SQLModel/asyncpg, Redis pub/sub, OpenAI SDK (backend) · Next.js 15, TypeScript, Zustand, Vitest + @testing-library/react (frontend)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `frontend/lib/store.ts` | Add `continueToRun` action (transitions run without clearing chatMessages) |
| Modify | `frontend/lib/__tests__/store.test.ts` | Tests for `continueToRun` |
| Modify | `frontend/lib/api.ts` | Add `continueRun(runId, message)` fetch call |
| Modify | `frontend/components/ChatPanel.tsx` | Example chips (completed + empty), async send → `continueRun` |
| Modify | `frontend/components/__tests__/ChatPanel.test.tsx` | Tests for chips and continueRun wiring |
| Modify | `frontend/components/AgentStream.tsx` | Add agent bubble on `done` when chatMessages non-empty |
| Create | `frontend/components/__tests__/AgentStream.test.tsx` | Tests for agent bubble behaviour |
| Modify | `backend/src/agent/loop.py` | Add `format_result_context()` and `run_agent_continuation()` |
| Modify | `backend/src/agent/__init__.py` | Export `run_agent_continuation` |
| Modify | `backend/api/routes/analyze.py` | Add `POST /api/runs/{run_id}/continue` endpoint |
| Modify | `backend/tests/test_agent_loop.py` | Tests for `format_result_context` and `run_agent_continuation` |
| Modify | `backend/tests/test_analyze_route.py` | Tests for `/continue` endpoint |

---

## Task 1: Add `continueToRun` store action

**Files:**
- Modify: `frontend/lib/store.ts`
- Modify: `frontend/lib/__tests__/store.test.ts`

- [ ] **Step 1: Write failing tests**

Add these tests at the bottom of the `describe("useRunStore — chat state", ...)` block in `frontend/lib/__tests__/store.test.ts`:

```typescript
  it("continueToRun sets runId and status to running without clearing chatMessages", () => {
    useRunStore.getState().addChatMessage({ id: "1", role: "user", content: "hello", timestamp: 0 });
    useRunStore.getState().continueToRun("run-cont", params);
    const { runId, status, chatMessages } = useRunStore.getState();
    expect(runId).toBe("run-cont");
    expect(status).toBe("running");
    expect(chatMessages).toHaveLength(1);
  });

  it("continueToRun clears pendingPreRunMessages", () => {
    useRunStore.getState().queuePreRunMessage("x");
    useRunStore.getState().continueToRun("run-cont", params);
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });

  it("continueToRun writes runId to sessionStorage", () => {
    useRunStore.getState().continueToRun("run-cont", params);
    expect(sessionStorage.getItem("activeRunId")).toBe("run-cont");
  });

  it("continueToRun resets result and error", () => {
    useRunStore.getState().continueToRun("run-cont", params);
    expect(useRunStore.getState().result).toBeNull();
    expect(useRunStore.getState().error).toBeNull();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose lib/__tests__/store.test.ts
```

Expected: 4 new tests fail — `continueToRun` does not exist.

- [ ] **Step 3: Add `continueToRun` to `frontend/lib/store.ts`**

Add `continueToRun: (runId: string, params: LastRunParams) => void;` to the `RunStore` type (after `clearPreRunMessages`):

```typescript
  continueToRun: (runId: string, params: LastRunParams) => void;
```

Add the implementation to the store (after `clearPreRunMessages`):

```typescript
  continueToRun: (runId, params) => {
    sessionStorage.setItem(RUN_ID_KEY, runId);
    sessionStorage.removeItem(MESSAGES_KEY);
    // chatMessages intentionally preserved — user bubble and agent response must survive the run transition
    set({
      runId,
      status: "running",
      result: null,
      error: null,
      messages: [],
      lastRunParams: params,
      pendingPreRunMessages: [],
    });
  },
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose lib/__tests__/store.test.ts
```

Expected: ALL tests pass.

- [ ] **Step 5: Run type-check**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/store.ts frontend/lib/__tests__/store.test.ts
git commit -m "feat(store): add continueToRun action — transitions run without clearing chatMessages"
```

---

## Task 2: Add `continueRun` API call

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add `continueRun` to `frontend/lib/api.ts`**

Add to the `api` object (after `cancelRun`):

```typescript
  continueRun: (runId: string, message: string) =>
    request<{ run_id: string }>(`/api/runs/${runId}/continue`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
```

- [ ] **Step 2: Run type-check**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): add continueRun call — POST /api/runs/{id}/continue"
```

---

## Task 3: Backend — `format_result_context` and `run_agent_continuation`

**Files:**
- Modify: `backend/src/agent/loop.py`
- Modify: `backend/src/agent/__init__.py`
- Modify: `backend/tests/test_agent_loop.py`

- [ ] **Step 1: Write failing tests**

Add these tests at the bottom of `backend/tests/test_agent_loop.py`. First, update the import at the top of the file to include the new symbols:

```python
from src.agent.loop import (
    RunCanceled,
    build_system_prompt,
    estimate_tabpfn_calls,
    format_result_context,
    phase_for_tool,
    run_agent_continuation,
    run_agent_loop,
    tabpfn_calls_for_tool,
)
```

Then add these tests at the bottom:

```python
def test_format_result_context_includes_all_fields() -> None:
    result = {
        "regime": {"regime": "range_bound", "confidence": 0.82},
        "direction": {"direction": "up", "confidence": 0.71},
        "drift": {
            "drift_detected": True,
            "psi_score": 0.23,
            "drifted_features": ["CL=F_roc_20d"],
        },
        "feature_importance": {
            "top_features": [{"name": "CL=F_roc_20d", "importance": 0.18}]
        },
        "summary": "Markets look range-bound.",
    }
    ctx = format_result_context(result, "2023-01-01", "2023-06-30")
    assert "2023-01-01 to 2023-06-30" in ctx
    assert "range_bound" in ctx
    assert "0.82" in ctx
    assert "up" in ctx
    assert "0.71" in ctx
    assert "True" in ctx
    assert "CL=F_roc_20d" in ctx
    assert "0.18" in ctx
    assert "Markets look range-bound." in ctx


def test_format_result_context_handles_missing_fields() -> None:
    ctx = format_result_context({"summary": "Minimal."}, "2023-01-01", "2023-06-30")
    assert "Minimal." in ctx
    assert "Regime" not in ctx
    assert "Drift" not in ctx


def test_format_result_context_handles_no_drifted_features() -> None:
    result = {"drift": {"drift_detected": False, "psi_score": 0.01, "drifted_features": []}}
    ctx = format_result_context(result, "2023-01-01", "2023-06-30")
    assert "none" in ctx


@pytest.mark.asyncio
async def test_run_agent_continuation_marks_completed_on_stop_response() -> None:
    run = MagicMock()
    run.status = RunStatus.RUNNING
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="The drift is elevated because...", tool_calls=None),
                )
            ],
        )
    )

    messages = [
        {"role": "system", "content": "You are an analyst."},
        {"role": "user", "content": "Previous analysis result (2023-01-01 to 2023-06-30):\nSummary: done."},
        {"role": "user", "content": "Why is drift elevated?"},
    ]

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", return_value=openai_client),
    ):
        await run_agent_continuation(uuid.uuid4(), messages, "2023-01-01", "2023-06-30")

    assert run.status == RunStatus.COMPLETED
    published = [json.loads(call.args[1]) for call in redis_client.publish.await_args_list]
    assert any(m.get("type") == "done" for m in published)
    done_msg = next(m for m in published if m.get("type") == "done")
    assert "elevated" in done_msg["summary"]


@pytest.mark.asyncio
async def test_run_agent_continuation_marks_failed_on_error() -> None:
    run = MagicMock()
    run.status = RunStatus.RUNNING
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        await run_agent_continuation(uuid.uuid4(), [], "2023-01-01", "2023-06-30")

    assert run.status == RunStatus.FAILED
    assert "boom" in run.error
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run pytest tests/test_agent_loop.py::test_format_result_context_includes_all_fields tests/test_agent_loop.py::test_run_agent_continuation_marks_completed_on_stop_response -v
```

Expected: FAIL — `format_result_context` and `run_agent_continuation` not defined.

- [ ] **Step 3: Add `format_result_context` to `backend/src/agent/loop.py`**

Add this function before `run_agent_loop` (e.g., after `phase_for_tool`):

```python
def format_result_context(
    result: dict[str, Any],
    date_range_start: str,
    date_range_end: str,
) -> str:
    """Format a Run.result dict as a readable LLM context message."""
    lines = [f"Previous analysis result ({date_range_start} to {date_range_end}):"]

    regime = result.get("regime")
    if isinstance(regime, dict):
        lines.append(
            f"Regime: {regime.get('regime')} (confidence {regime.get('confidence', 0):.2f})"
        )

    direction = result.get("direction")
    if isinstance(direction, dict):
        lines.append(
            f"Direction: {direction.get('direction')} (confidence {direction.get('confidence', 0):.2f})"
        )

    drift = result.get("drift")
    if isinstance(drift, dict):
        detected = drift.get("drift_detected", False)
        psi = drift.get("psi_score", 0)
        features = drift.get("drifted_features") or []
        features_str = ", ".join(features) if features else "none"
        lines.append(
            f"Drift detected: {detected}, PSI score {psi:.2f}, drifted features: {features_str}"
        )

    fi = result.get("feature_importance")
    if isinstance(fi, dict):
        top = (fi.get("top_features") or [])[:3]
        if top:
            top_str = ", ".join(f"{f['name']} ({f['importance']:.2f})" for f in top)
            lines.append(f"Top features: {top_str}")

    summary = result.get("summary", "")
    if summary:
        lines.append(f"Summary: {summary}")

    return "\n".join(lines)
```

- [ ] **Step 4: Add `run_agent_continuation` to `backend/src/agent/loop.py`**

Add this function after `run_agent_loop`:

```python
async def run_agent_continuation(
    run_id: uuid.UUID,
    messages: list[dict],  # type: ignore[type-arg]
    date_range_start: str,
    date_range_end: str,
) -> None:
    """Drive the ReAct loop for a post-run continuation.

    Takes a pre-built messages list [system, result_context, user_message].
    Creates its own DB session and Redis connection.
    """
    redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)  # type: ignore[type-arg]
    channel = f"run:{run_id}"
    _tabpfn_progress.register_run(str(run_id))

    try:
        await _raise_if_canceled(run_id)
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.status = RunStatus.RUNNING
            await session.commit()

        openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        context = AgentContext(
            date_range_start=date_range_start,
            date_range_end=date_range_end,
        )

        log.info("agent.continuation.start", run_id=str(run_id), model=settings.agent_model)
        await _publish_phase(redis_client, channel, run_id, "starting")

        last_text = ""
        total_input_tokens = 0
        total_output_tokens = 0

        for _ in range(MAX_ITERATIONS):
            await _raise_if_canceled(run_id)
            response = await openai_client.chat.completions.create(
                model=settings.agent_model,
                tools=registry.schemas(),  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens
            choice = response.choices[0]

            if choice.message.content:
                last_text = choice.message.content
                await _publish(redis_client, channel, {"type": "thought", "content": last_text})

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                assistant_msg: dict = {  # type: ignore[type-arg]
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments,  # type: ignore[union-attr]
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    name = tc.function.name  # type: ignore[union-attr]
                    arguments = json.loads(tc.function.arguments)  # type: ignore[union-attr]
                    await _raise_if_canceled(run_id)
                    await _publish_phase(
                        redis_client, channel, run_id, phase_for_tool(name, arguments), tool=name
                    )
                    await _publish(
                        redis_client, channel, {"type": "tool_call", "tool": name, "input": arguments}
                    )
                    log.info("agent.tool.start", run_id=str(run_id), tool=name)
                    _t0 = perf_counter()
                    try:
                        result = await asyncio.to_thread(registry.dispatch, name, arguments, context)
                    except _tabpfn_progress.RunCanceledInThread:
                        raise RunCanceled
                    finally:
                        _tabpfn_progress.set_callback(None)
                    _ms = round((perf_counter() - _t0) * 1000)
                    log.info("agent.tool.done", run_id=str(run_id), tool=name, duration_ms=_ms)
                    await _raise_if_canceled(run_id)
                    await _publish(
                        redis_client, channel, {"type": "tool_result", "tool": name, "output": result}
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                break
        else:
            raise RuntimeError(f"Agent loop exceeded max iterations ({MAX_ITERATIONS})")

        estimated_cost = (
            total_input_tokens / 1000 * settings.agent_model_input_cost_per_1k
            + total_output_tokens / 1000 * settings.agent_model_output_cost_per_1k
        )
        usage = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
        }

        log.info("agent.continuation.done", run_id=str(run_id), model=settings.agent_model, **usage)
        await _publish_phase(redis_client, channel, run_id, "completed")
        await _publish(
            redis_client, channel, {"type": "done", "summary": last_text, "usage": usage}
        )

        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "drift": context.drift_result,
                    "feature_importance": context.shap_result,
                    "backtest": context.backtest_result,
                    "summary": last_text,
                    "usage": usage,
                    "data_manifest": context.data_manifest,
                }
                await session.commit()

    except RunCanceled:
        await _publish_phase(redis_client, channel, run_id, "canceled")
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.CANCELED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.error = run.error or "Canceled by user"
                await session.commit()

    except Exception as exc:
        log.error("agent.continuation.error", run_id=str(run_id), error=str(exc), exc_info=True)
        await _publish_phase(redis_client, channel, run_id, "failed")
        await _publish(redis_client, channel, {"type": "error", "message": str(exc)})
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                await session.commit()

    finally:
        _tabpfn_progress.unregister_run(str(run_id))
        await redis_client.aclose()  # type: ignore[attr-defined]
```

- [ ] **Step 5: Export `run_agent_continuation` from `backend/src/agent/__init__.py`**

Replace the entire file with:

```python
from src.agent.loop import run_agent_continuation, run_agent_loop

__all__ = ["run_agent_continuation", "run_agent_loop"]
```

- [ ] **Step 6: Run failing tests to verify they now pass**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run pytest tests/test_agent_loop.py -k "format_result_context or run_agent_continuation" -v
```

Expected: 5 new tests pass.

- [ ] **Step 7: Run full agent loop test suite**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run pytest tests/test_agent_loop.py -v
```

Expected: ALL tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agent/loop.py backend/src/agent/__init__.py backend/tests/test_agent_loop.py
git commit -m "feat(agent): add format_result_context and run_agent_continuation"
```

---

## Task 4: Backend — `/continue` endpoint

**Files:**
- Modify: `backend/api/routes/analyze.py`
- Modify: `backend/tests/test_analyze_route.py`

- [ ] **Step 1: Write failing tests**

Add these tests at the bottom of `backend/tests/test_analyze_route.py`. First update imports at the top to add `run_agent_continuation`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from src.db.session import get_session
from src.db.models import RunStatus
```

Then add these test functions:

```python
def _make_completed_run(
    run_id: str = "00000000-0000-0000-0000-000000000001",
) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.status = RunStatus.COMPLETED
    run.result = {
        "summary": "Range-bound regime detected.",
        "regime": {"regime": "range_bound", "confidence": 0.82},
        "direction": None,
        "drift": None,
        "feature_importance": None,
        "backtest": None,
    }
    run.date_range_start = "2023-01-01"
    run.date_range_end = "2023-06-30"
    run.tasks = ["regime_classification"]
    return run


def test_continue_run_returns_202_with_new_run_id() -> None:
    source_run = _make_completed_run()
    new_run = MagicMock()
    new_run.id = "00000000-0000-0000-0000-000000000002"

    call_count = 0

    async def override_session():  # type: ignore[return]
        nonlocal call_count
        mock_session = AsyncMock()
        if call_count == 0:
            mock_session.get.return_value = source_run
        else:
            mock_session.get.return_value = new_run
            mock_session.refresh = AsyncMock(return_value=None)
        call_count += 1
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_continuation"):
            client = TestClient(app)
            response = client.post(
                "/api/runs/00000000-0000-0000-0000-000000000001/continue",
                json={"message": "Why is drift elevated?"},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert "run_id" in response.json()


def test_continue_run_returns_404_for_missing_source_run() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = None
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs/00000000-0000-0000-0000-000000000099/continue",
            json={"message": "hello"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404


def test_continue_run_returns_409_if_source_not_completed() -> None:
    source_run = MagicMock()
    source_run.status = RunStatus.RUNNING

    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.get.return_value = source_run
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs/00000000-0000-0000-0000-000000000001/continue",
            json={"message": "hello"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409


def test_continue_run_returns_422_for_invalid_run_id() -> None:
    client = TestClient(app)
    response = client.post("/api/runs/not-a-uuid/continue", json={"message": "hello"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run pytest tests/test_analyze_route.py::test_continue_run_returns_202_with_new_run_id tests/test_analyze_route.py::test_continue_run_returns_404_for_missing_source_run -v
```

Expected: FAIL — endpoint does not exist yet.

- [ ] **Step 3: Add the `/continue` endpoint to `backend/api/routes/analyze.py`**

Add these imports at the top of the file (after the existing imports):

```python
from src.agent import run_agent_continuation
from src.agent.loop import build_system_prompt, format_result_context
```

Add these Pydantic models after `CancelRunResponse`:

```python
class ContinueRequest(BaseModel):
    message: str


class ContinueResponse(BaseModel):
    run_id: str
```

Add this endpoint after the `cancel_run` handler:

```python
@router.post(
    "/runs/{run_id}/continue",
    response_model=ContinueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def continue_run(
    run_id: str,
    request: ContinueRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> ContinueResponse:
    try:
        source_uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    source_run = await session.get(Run, source_uid)
    if source_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if source_run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Source run is not completed"
        )
    if source_run.result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Source run has no result"
        )

    context_str = format_result_context(
        source_run.result,
        source_run.date_range_start,
        source_run.date_range_end,
    )
    messages: list[dict] = [  # type: ignore[type-arg]
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": context_str},
        {"role": "user", "content": request.message},
    ]

    new_run = Run(
        date_range_start=source_run.date_range_start,
        date_range_end=source_run.date_range_end,
        tasks=source_run.tasks,
    )
    session.add(new_run)
    await session.commit()
    await session.refresh(new_run)

    background_tasks.add_task(
        run_agent_continuation,
        new_run.id,
        messages,
        source_run.date_range_start,
        source_run.date_range_end,
    )

    return ContinueResponse(run_id=str(new_run.id))
```

- [ ] **Step 4: Run all route tests**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run pytest tests/test_analyze_route.py -v
```

Expected: ALL tests pass (existing + 4 new).

- [ ] **Step 5: Run full backend test suite**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run python -m pytest
```

Expected: ALL tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/analyze.py backend/tests/test_analyze_route.py
git commit -m "feat(api): add POST /api/runs/{run_id}/continue endpoint"
```

---

## Task 5: ChatPanel — example chips and continueRun wiring

**Files:**
- Modify: `frontend/components/ChatPanel.tsx`
- Modify: `frontend/components/__tests__/ChatPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

Add these tests at the bottom of `frontend/components/__tests__/ChatPanel.test.tsx`.

First, add mock setup at the top of the file (after the existing `vi.mock` calls if any, or add at the top):

```typescript
const { mockContinueRun } = vi.hoisted(() => ({
  mockContinueRun: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: { continueRun: mockContinueRun },
}));
```

Update `beforeEach` to clear the new mock:

```typescript
beforeEach(() => {
  vi.clearAllMocks();
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});
```

Then add these test blocks at the bottom:

```typescript
describe("ChatPanel — example chips", () => {
  it("shows example chips when status is completed and chatMessages is empty", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    expect(screen.getByText(/why is drift elevated/i)).toBeTruthy();
    expect(screen.getByText(/explain the regime/i)).toBeTruthy();
    expect(screen.getByText(/add baker hughes/i)).toBeTruthy();
    expect(screen.getByText(/top features/i)).toBeTruthy();
  });

  it("does not show chips when status is idle", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    expect(screen.queryByText(/why is drift elevated/i)).toBeNull();
  });

  it("does not show chips when chatMessages is non-empty", () => {
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "r1",
      chatMessages: [{ id: "1", role: "user", content: "hi", timestamp: 0 }],
    });
    render(<ChatPanel />);
    expect(screen.queryByText(/why is drift elevated/i)).toBeNull();
  });

  it("clicking a chip populates the textarea without sending", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    fireEvent.click(screen.getByText(/why is drift elevated/i));
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    expect((textarea as HTMLTextAreaElement).value).toBe("Why is drift elevated?");
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
  });
});

describe("ChatPanel — continueRun on completed send", () => {
  it("calls continueRun and continueToRun when sending while completed", async () => {
    mockContinueRun.mockResolvedValueOnce({ run_id: "run-new" });
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    fireEvent.change(textarea, { target: { value: "Why is drift elevated?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(mockContinueRun).toHaveBeenCalledWith("run-old", "Why is drift elevated?");
      expect(useRunStore.getState().runId).toBe("run-new");
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("adds user message to chatMessages before calling continueRun", async () => {
    mockContinueRun.mockResolvedValueOnce({ run_id: "run-new" });
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    fireEvent.change(screen.getByPlaceholderText(/ask a follow-up/i), {
      target: { value: "Explain drift" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(useRunStore.getState().chatMessages).toHaveLength(1);
      expect(useRunStore.getState().chatMessages[0].content).toBe("Explain drift");
    });
  });

  it("preserves chatMessages on continueRun error", async () => {
    mockContinueRun.mockRejectedValueOnce(new Error("network error"));
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    fireEvent.change(screen.getByPlaceholderText(/ask a follow-up/i), {
      target: { value: "Explain drift" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(useRunStore.getState().status).toBe("completed");
      expect(useRunStore.getState().chatMessages).toHaveLength(1);
    });
  });
});
```

Also add `waitFor` to the imports at the top:

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose components/__tests__/ChatPanel.test.tsx
```

Expected: existing tests pass; new tests fail.

- [ ] **Step 3: Update `frontend/components/ChatPanel.tsx`**

Replace the entire file with:

```typescript
"use client";

import { useRef, useState } from "react";
import { useRunStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/store";

const EXAMPLE_CHIPS = [
  "Why is drift elevated?",
  "Explain the regime classification",
  "Add Baker Hughes rig count data",
  "What are the top features driving this?",
];

export function ChatPanel() {
  const {
    chatOpen,
    chatMessages,
    status,
    runId,
    lastRunParams,
    setChatOpen,
    addChatMessage,
    queuePreRunMessage,
    continueToRun,
  } = useRunStore();
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  if (!chatOpen) return null;

  const isInputDisabled =
    status === "running" || status === "failed" || status === "canceled";

  const placeholder =
    status === "running"
      ? "Agent is working — message will be queued"
      : status === "completed"
        ? "Ask a follow-up question…"
        : status === "failed" || status === "canceled"
          ? "Run ended"
          : "Ask the agent — add a connector, set context…";

  const showChips = status === "completed" && chatMessages.length === 0;

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isInputDisabled || isSending) return;

    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };

    if (status === "completed" && runId && lastRunParams) {
      setIsSending(true);
      setInput("");
      addChatMessage(msg);
      try {
        const { run_id } = await api.continueRun(runId, trimmed);
        continueToRun(run_id, lastRunParams);
      } catch {
        // continuation failed — status stays completed, user message preserved in chat
      } finally {
        setIsSending(false);
      }
    } else {
      addChatMessage(msg);
      if (status === "idle") queuePreRunMessage(trimmed);
      setInput("");
    }

    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <aside className="w-[280px] border-l border-slate-800 flex flex-col bg-[#0f0f1a] shrink-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
        <span className="text-sm font-semibold text-slate-300">Chat</span>
        <button
          onClick={() => setChatOpen(false)}
          className="text-slate-500 hover:text-slate-300 text-sm leading-none"
          aria-label="Close chat"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 min-h-0 flex flex-col justify-end gap-2">
        {chatMessages.length === 0 && !showChips && (
          <p className="text-xs text-slate-500 text-center">
            Messages appear here.
          </p>
        )}
        {showChips && (
          <div className="flex flex-col gap-1 mb-2">
            <p className="text-xs text-slate-500 text-center mb-1">Try asking…</p>
            {EXAMPLE_CHIPS.map((chip) => (
              <button
                key={chip}
                onClick={() => setInput(chip)}
                className="text-left text-xs px-2 py-1.5 rounded border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-300 transition-colors"
              >
                {chip}
              </button>
            ))}
          </div>
        )}
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-lg px-3 py-2 max-w-[85%] text-sm"
                  : "bg-slate-800 text-slate-200 rounded-lg px-3 py-2 max-w-[85%] text-sm"
              }
            >
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-800 p-2 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isInputDisabled}
          placeholder={placeholder}
          rows={2}
          className={
            "flex-1 resize-none rounded border border-slate-700 bg-slate-900 text-slate-100 " +
            "text-sm px-2 py-1 focus:outline-none focus:ring-1 focus:ring-violet-500 " +
            "disabled:opacity-50 disabled:cursor-not-allowed"
          }
        />
        <button
          onClick={handleSend}
          disabled={isInputDisabled || isSending || !input.trim()}
          aria-label="Send message"
          className={
            "px-2 py-1 rounded bg-violet-600 hover:bg-violet-700 text-white text-sm " +
            "font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          }
        >
          ↑
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 4: Run all ChatPanel tests**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose components/__tests__/ChatPanel.test.tsx
```

Expected: ALL tests pass (existing + new).

- [ ] **Step 5: Run type-check**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ChatPanel.tsx frontend/components/__tests__/ChatPanel.test.tsx
git commit -m "feat(chat): add example chips and continueRun wiring for completed state"
```

---

## Task 6: AgentStream — add agent bubble on `done`

**Files:**
- Modify: `frontend/components/AgentStream.tsx`
- Create: `frontend/components/__tests__/AgentStream.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/components/__tests__/AgentStream.test.tsx`:

```typescript
import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AgentStream } from "../AgentStream";
import { useRunStore } from "@/lib/store";
import type { StreamMessage } from "@/lib/websocket";

const { mockGetRun, mockUseRunStream } = vi.hoisted(() => ({
  mockGetRun: vi.fn(),
  mockUseRunStream: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: { getRun: mockGetRun },
}));
vi.mock("@/lib/websocket", () => ({
  useRunStream: mockUseRunStream,
}));

const doneMessage: StreamMessage = {
  type: "done",
  summary: "The drift is elevated because of macro shifts.",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseRunStream.mockReturnValue({ messages: [], connected: false });
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});

describe("AgentStream — agent bubble on done", () => {
  it("adds agent bubble to chatMessages when done arrives and chatMessages is non-empty", async () => {
    mockGetRun.mockResolvedValueOnce({
      status: "completed",
      result: { summary: "done", regime: null, direction: null, drift: null, feature_importance: null, backtest: null, usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 }, data_manifest: null },
    });
    useRunStore.setState({
      runId: "run-1",
      status: "running",
      chatMessages: [{ id: "1", role: "user", content: "Why is drift elevated?", timestamp: 0 }],
    });
    mockUseRunStream.mockReturnValue({ messages: [doneMessage], connected: true });

    render(<AgentStream />);

    await vi.waitFor(() => {
      const { chatMessages } = useRunStore.getState();
      expect(chatMessages).toHaveLength(2);
      expect(chatMessages[1].role).toBe("agent");
      expect(chatMessages[1].content).toBe("The drift is elevated because of macro shifts.");
    });
  });

  it("does NOT add agent bubble when done arrives and chatMessages is empty", async () => {
    mockGetRun.mockResolvedValueOnce({
      status: "completed",
      result: { summary: "done", regime: null, direction: null, drift: null, feature_importance: null, backtest: null, usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 }, data_manifest: null },
    });
    useRunStore.setState({ runId: "run-1", status: "running", chatMessages: [] });
    mockUseRunStream.mockReturnValue({ messages: [doneMessage], connected: true });

    render(<AgentStream />);

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe("completed");
    });
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose components/__tests__/AgentStream.test.tsx
```

Expected: FAIL — no agent bubble logic yet.

- [ ] **Step 3: Update `frontend/components/AgentStream.tsx`**

Replace the entire file with:

```typescript
"use client";

import { useEffect, useRef } from "react";
import { useRunStore } from "@/lib/store";
import { useRunStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import type { AnalysisResult } from "@/lib/api";

export function AgentStream() {
  const { runId, status, setResult, setStatus, setError, setMessages, clearRun, addChatMessage } =
    useRunStore();
  const { messages: wsMessages } = useRunStream(runId);

  const mountRunId = useRef(runId);
  const mountStatus = useRef(status);
  const baselineMessages = useRef(useRunStore.getState().messages);

  useEffect(() => {
    const restoredRunId = mountRunId.current;
    const restoredStatus = mountStatus.current;
    if (!restoredRunId || restoredStatus !== "idle") return;

    setStatus("running");
    api
      .getRun(restoredRunId)
      .then((run) => {
        if (run.status === "completed") {
          if (run.result) setResult(run.result as AnalysisResult);
          else setError("Run completed but no result was returned.");
        } else if (run.status === "failed") {
          setError("Run failed.");
        } else if (run.status === "canceled") {
          clearRun();
        }
      })
      .catch(() => clearRun());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const baseline = baselineMessages.current;
    setMessages(baseline.length > 0 ? [...baseline, ...wsMessages] : wsMessages);
  }, [wsMessages, setMessages]);

  useEffect(() => {
    const last = wsMessages[wsMessages.length - 1];
    if (last?.type !== "done" || !runId || status === "completed") return;

    const summary = last.summary;

    api
      .getRun(runId)
      .then((runResult) => {
        if (runResult.result) {
          setResult(runResult.result as AnalysisResult);
          // Add agent bubble if this was a continuation (user had sent a message)
          const currentChatMessages = useRunStore.getState().chatMessages;
          if (currentChatMessages.length > 0) {
            addChatMessage({
              id: crypto.randomUUID(),
              role: "agent",
              content: summary,
              timestamp: Date.now(),
            });
          }
        } else {
          setStatus("failed");
        }
      })
      .catch(() => setStatus("failed"));
  }, [wsMessages, runId, status, setResult, setStatus, addChatMessage]);

  return null;
}
```

- [ ] **Step 4: Run AgentStream tests**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test -- --reporter=verbose components/__tests__/AgentStream.test.tsx
```

Expected: ALL tests pass.

- [ ] **Step 5: Run full frontend test suite**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test
```

Expected: ALL tests pass.

- [ ] **Step 6: Run type-check**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/AgentStream.tsx frontend/components/__tests__/AgentStream.test.tsx
git commit -m "feat(stream): add agent bubble to chat panel when done arrives on continuation"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full backend lint + type-check**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run ruff check . && uv run mypy src/ api/
```

Expected: no ruff errors; no new mypy errors in touched files.

- [ ] **Step 2: Full backend test suite**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/backend && uv run python -m pytest
```

Expected: ALL tests pass.

- [ ] **Step 3: Full frontend type-check + lint**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run type-check && npm run lint
```

Expected: no errors.

- [ ] **Step 4: Full frontend test suite**

```bash
cd /Users/sulmae/xuemei/projects/signalyst/frontend && npm run test
```

Expected: ALL tests pass.

- [ ] **Step 5: Confirm git log**

```bash
git log --oneline feat/chat-window-pr2 ^main
```

Expected: ~8 commits since branching from main.
