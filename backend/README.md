# Backend

FastAPI + asyncpg backend for TemporalAgent. Streams LLM agent reasoning over WebSocket while persisting run state to PostgreSQL.

## Running

```bash
# From repo root
make dev-backend        # FastAPI with hot reload on :8000 (requires .env)
make dev                # Full stack via docker-compose (includes Redis + Postgres)

# Testing
cd backend && uv run python -m pytest
cd backend && uv run pytest tests/test_health.py  # single file

# Linting / type-checking
uv run ruff check .
uv run mypy .
```

## REST API

Base path: `/api`

---

### `POST /api/analyze`

Starts a new analysis run. Returns immediately; the agent loop runs in the background.

**Request body**

```json
{
  "date_range_start": "2023-01-01",
  "date_range_end":   "2024-01-01",
  "tasks": ["regime_classification", "price_direction", "equity_outperformance"],
  "analysis_mode": "quick"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `date_range_start` | `string` (YYYY-MM-DD) | required | Start of the analysis window |
| `date_range_end` | `string` (YYYY-MM-DD) | required | End of the analysis window |
| `tasks` | `string[]` | `["regime_classification", "price_direction", "equity_outperformance"]` | Tasks to run. Include `"backtest"` or `"historical_validation"` to force backtesting in quick mode. |
| `analysis_mode` | `"quick"` \| `"full"` | `"quick"` | Quick runs fewer TabPFN samples and skips backtest unless explicitly requested. Full mode runs exhaustive walk-forward backtest. |

**Response** — `202 Accepted`

```json
{ "run_id": "550e8400-e29b-41d4-a716-446655440000" }
```

---

### `GET /api/runs/{run_id}`

Polls the current state of a run.

**Response** — `200 OK`

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": { ... },
  "error": null
}
```

`status` values: `pending` | `running` | `completed` | `failed` | `canceled`

`result` is `null` unless `status == "completed"`. Shape matches `AnalysisResult` in `frontend/lib/api.ts`.

Returns `404` if `run_id` not found; `422` if `run_id` is not a valid UUID.

---

### `POST /api/runs/{run_id}/cancel`

Cancels a run that is still `pending` or `running`. Idempotent cancellations are rejected with `409` for runs already in a terminal state.

**Response** — `200 OK`

```json
{ "run_id": "...", "status": "canceled" }
```

---

### `GET /api/history`

Returns the 20 most recent runs ordered by creation time (newest first).

**Response** — `200 OK`

```json
[
  { "run_id": "...", "status": "completed", "result": { ... }, "error": null },
  ...
]
```

> **Note:** `backend/api/routes/history.py` contains a duplicate `/history` route that returns `501 Not Implemented`. It is unreachable because `analyze.py` registers the same path first, but it should be removed to avoid confusion.

---

### `POST /api/derivatives/price`

Returns `501 Not Implemented`. Placeholder for Monte Carlo option pricing (GBM/Heston). Implementation lives in `src/derivatives/` but the route is not yet wired up.

---

## WebSocket

```
ws://localhost:8000/ws/runs/{run_id}/stream
```

Connect after calling `POST /api/analyze`. The server subscribes to the Redis channel `run:{run_id}` and forwards every published message as a JSON frame. The connection stays open until the agent finishes or the client disconnects.

### Message types

All messages are JSON objects with a `type` field.

| `type` | Fields | Description |
|---|---|---|
| `phase` | `phase: string`, `tool: string \| null` | Agent moved to a new execution phase (see phases below) |
| `thought` | `content: string` | LLM reasoning text (streamed as the model thinks) |
| `tool_call` | `tool: string`, `input: object` | Tool the agent is about to invoke |
| `tool_result` | `tool: string`, `output: object` | Result returned by a tool |
| `tabpfn_progress` | `completed_calls: int`, `known_calls: int`, `unknown_backtest: bool`, `note: string`, `tool: string \| null` | Progress toward estimated TabPFN call count |
| `tabpfn_estimate` | `known_calls: int`, `unknown_backtest: bool`, `note: string` | Initial estimate published before the loop starts |
| `done` | `summary: string`, `usage: object` | Agent finished successfully. `usage` contains `input_tokens`, `output_tokens`, `estimated_cost_usd`. |
| `error` | `message: string` | Unrecoverable error; run status set to `failed`. |

---

## Agent Loop

`src/agent/loop.py` implements the ReAct loop using the OpenAI SDK (model: `gpt-5.5` / `gpt-5.5-mini` for quick mode).

### Phases

Phases are broadcast as `phase` messages. The frontend uses them to drive the progress timeline.

| Phase | Triggered by |
|---|---|
| `starting` | Loop startup |
| `fetching_market_data` | `fetch_data` tool call |
| `fetching_geopolitical_risk` | `fetch_geopolitical_risk` tool call |
| `engineering_features` | `engineer_features` tool call |
| `detecting_drift` | `detect_drift` tool call |
| `predicting_regime` | `run_tabpfn` with `task="regime"` |
| `predicting_direction` | `run_tabpfn` with `task="direction"` |
| `evaluating_features` | `evaluate_features` tool call |
| `backtesting` | `backtest` tool call |
| `explaining` | `explain_prediction` tool call |
| `completed` / `failed` / `canceled` | Terminal states |

### Tools

| Tool | Description |
|---|---|
| `fetch_data` | Pulls WTI (CL=F), DXY, XLE, SPY prices and INDPRO macro series from yfinance / FRED |
| `fetch_geopolitical_risk` | Adds the GPR (Geopolitical Risk) index to the signal set |
| `engineer_features` | Featurizes time-series into tabular snapshots: rolling stats, lags, momentum, regime features |
| `detect_drift` | Checks whether recent feature distributions have shifted relative to the training window |
| `run_tabpfn` | Runs TabPFN classification for `task="regime"` or `task="direction"` |
| `evaluate_features` | Computes permutation feature importances from the regime classifier (sklearn) |
| `backtest` | Walk-forward cross-validation: regime accuracy + direction strategy Sharpe vs SPY |
| `explain_prediction` | Assembles a natural-language explanation from model outputs and feature importances |

### Quick vs Full mode

| | Quick | Full |
|---|---|---|
| `evaluate_features` | `top_n=5, max_samples=5` | `top_n=10, max_samples=50` |
| `backtest` | Skipped unless tasks include `"backtest"` or `"historical_validation"` (max 3 windows) | Always runs, uncapped windows |
| Max iterations | 10 | 10 |

### Redis streaming

The loop publishes to `run:{run_id}` on every significant event. `api/ws.py` subscribes to that channel and forwards each frame to connected WebSocket clients. There is no persistence of stream messages in the database — clients that reconnect receive only messages published after they subscribe (or messages restored from `sessionStorage` on the frontend).
