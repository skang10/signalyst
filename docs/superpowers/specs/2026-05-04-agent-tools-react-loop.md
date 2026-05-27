# Agent Tools & ReAct Loop — Design Spec

**Session:** 4
**Branch:** `feat/agent-tools`
**Date:** 2026-05-04

---

## Goal

Implement the `src/agent/` package: a tool registry, 4 core tool functions, and an async ReAct loop that drives an OpenAI model to orchestrate the full oil-market analysis pipeline (fetch → featurize → classify → explain). The loop runs as a FastAPI `BackgroundTask`, publishes each reasoning step to Redis, and persists the final result in the `Run` DB row.

---

## Architecture

```
POST /api/analyze
    └── BackgroundTask: run_agent_loop(run_id, request, db_session)
            │
            ├── src/agent/registry.py   ← @tool decorator + ToolRegistry
            ├── src/agent/tools.py      ← 4 tool functions decorated with @tool
            └── src/agent/loop.py       ← ReAct loop (OpenAI chat completions)
                    │
                    ├── src/data/connectors.py   (fetch_data)
                    ├── src/featurizer/          (engineer_features)
                    ├── src/inference/           (run_tabpfn)
                    └── Redis pub/sub            (stream steps to WebSocket)
```

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/src/agent/registry.py` | `@tool` decorator + `ToolRegistry` singleton |
| Create | `backend/src/agent/tools.py` | 4 tool functions + `AgentContext` |
| Create | `backend/src/agent/loop.py` | async ReAct loop |
| Modify | `backend/src/agent/__init__.py` | re-export `run_agent_loop` |
| Modify | `backend/src/config.py` | add `openai_api_key`, `agent_model`, `agent_model_fast`, `redis_url` (already exists) |
| Modify | `backend/api/routes/analyze.py` | wire `BackgroundTask` → `run_agent_loop` |
| Create | `backend/tests/test_agent_tools.py` | unit tests for tool functions |

---

## Component Designs

### `registry.py` — Tool Registry

`ToolRegistry` is a module-level singleton. The `@tool` decorator registers a function under its name, storing: the callable, its docstring, and its OpenAI function schema (passed as a `parameters` argument to the decorator).

```python
registry = ToolRegistry()

def tool(parameters: dict):
    def decorator(fn):
        registry.register(fn, parameters)
        return fn
    return decorator
```

`registry.schemas()` → `list[dict]` in OpenAI function-calling format:
```json
[{
  "type": "function",
  "function": {
    "name": "fetch_data",
    "description": "...",
    "parameters": { "type": "object", "properties": {...}, "required": [...] }
  }
}]
```

`registry.dispatch(name, arguments, context)` → calls the registered function with `**arguments` and the shared `AgentContext`.

---

### `tools.py` — Tool Functions & AgentContext

`AgentContext` is a plain dataclass holding shared state across tool calls within one loop run:

```python
@dataclass
class AgentContext:
    date_range_start: str
    date_range_end: str
    signals: dict[str, pd.Series] = field(default_factory=dict)
    features: pd.DataFrame | None = None
    regime_result: dict | None = None
    direction_result: dict | None = None
```

**`fetch_data(tickers, fred_series, context)`**
- Calls `fetch_price_series(ticker, start, end)` for each ticker
- Calls `fetch_fred_series(series_id, start, end, api_key)` for each FRED series (skips if no key)
- Stores results in `context.signals`
- Returns `{"fetched": {name: row_count}, "skipped": [...]}`

**`engineer_features(windows, lags, context)`**
- Requires `context.signals` populated
- Calls `TimeSeriesFeaturizer(windows=windows, lags=lags).transform(context.signals)`
- Stores result in `context.features`
- Returns `{"shape": [rows, cols], "date_range": [start, end]}`

**`run_tabpfn(task, horizon, context)`**
- `task`: `"regime"` or `"direction"`
- Requires `context.features` populated
- 80/20 temporal split; fits `OilRegimeClassifier` or `DirectionClassifier`
- Stores result dict in `context.regime_result` or `context.direction_result`
- Returns `{"task": task, "predictions": {date.isoformat(): label}, "mean_confidence": float, "mean_entropy": float}` — dates converted to ISO strings for JSON serialisation

**`explain_prediction(regime, direction, confidence, key_features, context)`**
- Pure formatting function — assembles the inputs into a structured dict
- Returns `{"regime": regime, "direction": direction, "confidence": confidence, "key_features": key_features}`
- The agent uses this to ground its final natural language summary

---

### `loop.py` — ReAct Loop

```python
async def run_agent_loop(
    run_id: uuid.UUID,
    request: AnalyzeRequest,
) -> None
```

The loop creates its own `AsyncSession` from `engine` (imported from `src.db.session`). It must not reuse the session from the HTTP request — that session is closed once the response is sent.

**Flow:**

1. Mark `Run.status = RUNNING` in DB
2. Create `AgentContext(date_range_start, date_range_end)`
3. Build initial messages:
   - `system`: oil market analyst persona + instructions to use tools in order
   - `user`: `"Analyze {start} to {end}. Tasks: {tasks}"`
4. Loop up to `max_iterations=10`:
   - Call `openai_client.chat.completions.create(model=settings.agent_model, tools=registry.schemas(), messages=messages)`
   - For each text content block: publish `{"type": "thought", "content": text}` to Redis channel `run:{run_id}`
   - If `finish_reason == "tool_calls"`:
     - For each tool call:
       - Publish `{"type": "tool_call", "tool": name, "input": arguments}`
       - `result = registry.dispatch(name, arguments, context)`
       - Publish `{"type": "tool_result", "tool": name, "output": result}`
     - Append assistant message + tool result messages
   - If `finish_reason == "stop"`: break
5. Publish `{"type": "done", "summary": last_text_content}`
6. Mark `Run.status = COMPLETED`, `Run.result = {regime_result, direction_result}`
7. On any exception: mark `Run.status = FAILED`, `Run.error = str(e)`, publish `{"type": "error", "message": str(e)}`

**Redis publishing** uses `aioredis` (`redis.asyncio`): `await redis_client.publish(f"run:{run_id}", json.dumps(message))`.

---

### `analyze.py` route update

```python
@router.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> AnalyzeResponse:
    run = Run(date_range_start=request.date_range_start, date_range_end=request.date_range_end, tasks=request.tasks)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    background_tasks.add_task(run_agent_loop, run.id, request)
    return AnalyzeResponse(run_id=str(run.id))
```

---

## Config Changes

Add to `Settings`:

```python
openai_api_key: str = ""
agent_model: str = "gpt-5.4"
agent_model_fast: str = "gpt-5.4-mini"
```

---

## System Prompt

```
You are an oil market intelligence analyst. You have access to tools to fetch market data,
engineer features, run TabPFN classification, and explain predictions.

Given a date range and analysis tasks, use the tools in this order:
1. fetch_data — pull WTI, DXY, XLE, SPY price series and INDPRO macro data
2. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]
3. run_tabpfn — classify regime, then predict direction
4. explain_prediction — summarize the regime, direction, confidence, and key signals

After calling explain_prediction, write a concise natural language summary of your findings.
Ground your explanation in the actual feature values and confidence scores returned by the tools.
```

---

## Testing

**`tests/test_agent_tools.py`** — all tests call tool functions directly, no OpenAI calls:

| Test | What it checks |
|---|---|
| `test_fetch_data_returns_signal_summary` | Mocks `fetch_price_series`; asserts return dict has correct keys |
| `test_fetch_data_skips_fred_without_key` | Sets `fred_api_key=""`, asserts FRED series appear in `skipped` |
| `test_engineer_features_returns_shape` | Populates context with synthetic signals; asserts `shape` key present |
| `test_run_tabpfn_regime` | Mocks `OilRegimeClassifier`; asserts result has `mean_confidence` |
| `test_run_tabpfn_direction` | Mocks `DirectionClassifier`; same |
| `test_explain_prediction_passthrough` | No mocks; asserts output equals input fields |
| `test_full_loop_smoke` | `@pytest.mark.skipif(not settings.openai_api_key, ...)` — runs real loop end-to-end |

---

## Dependencies

Check `pyproject.toml` — required additions:
- `openai>=1.0.0`
- `redis[asyncio]>=5.0.0` (for `redis.asyncio`)

Both may already be present; verify before adding.

---

## Out of Scope (deferred to later sessions)

- `detect_drift`, `backtest`, `evaluate_features`, `fetch_geopolitical_risk` tools
- WebSocket → Redis subscriber wiring (Session 5)
- `GET /api/runs/{run_id}` and `GET /api/history` route implementations (Session 5)
