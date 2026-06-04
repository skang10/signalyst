# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install all dependencies
make install                      # uv sync --extra dev + npm install

# Development servers
make dev-backend                  # FastAPI with hot reload on :8000 (requires .env)
make dev-frontend                 # Next.js dev server on :3000
make dev                          # Full stack via docker-compose

# Testing
make test                         # Backend pytest + frontend vitest
# Backend only:
cd backend && uv run python -m pytest
# Single test file:
cd backend && uv run pytest tests/test_health.py
# Frontend only:
cd frontend && npm run test

# Linting / type-checking
make lint                         # ruff + mypy (backend) + eslint + tsc (frontend)
cd backend && uv run ruff check . # backend lint only
cd frontend && npm run type-check # frontend type check only

# Database
make migrate                      # alembic upgrade head
make db-revision msg="your msg"   # alembic revision --autogenerate

# Docker
make build                        # docker-compose build
make clean                        # docker-compose down -v
```

## Architecture

### Overview

Signalyst detects oil market regime shifts using macro, geopolitical, and energy signals. The core loop: fetch time-series data → featurize into tabular snapshots → classify regime and predict price direction with TabPFN → stream the LLM agent's ReAct reasoning to the frontend over WebSocket.

```
LLM Agent (Claude, tool use / ReAct loop)
    ↓ tools: fetch_data, engineer_features, run_tabpfn, backtest, detect_drift, explain…
TimeSeriesFeaturizer  →  Tabular Feature Matrix  →  TabPFN Inference Engine
```

### Backend (`backend/`)

Package manager: **uv** (`uv run <cmd>` activates the venv automatically).

- `src/config.py` — `Settings` (pydantic-settings). Reads `.env` from the project root (two levels up from `src/`).
- `src/agent/` — LLM agent, tools, ReAct loop (to be implemented)
- `src/featurizer/` — `TimeSeriesFeaturizer`: rolling stats, lag features, momentum, regime features; strict temporal ordering to prevent leakage
- `src/inference/` — `TabPFNClassifier`/`TabPFNRegressor` wrappers; regime classification + WTI direction prediction
- `src/data/` — connectors for yfinance, fredapi, EIA API
- `src/eval/` — walk-forward cross-validation, backtest, Sharpe metrics
- `src/derivatives/` — GBM/Heston Monte Carlo simulation, European/American options pricing, Greeks
- `src/db/` — SQLModel + asyncpg database models
- `api/main.py` — FastAPI app; CORS configured from `settings.cors_origins`; Sentry initialised in lifespan if `SENTRY_DSN` is set
- `api/routes/` — REST handlers: `POST /api/analyze`, `GET /api/runs/{run_id}`, `GET /api/history`, `POST /api/derivatives/price`
- `api/ws.py` — WebSocket handler at `/ws/runs/{run_id}/stream`; TODO: subscribe to Redis channel and forward messages

**WebSocket streaming protocol** (JSON lines over WS):
```json
{ "type": "thought",     "content": "..." }
{ "type": "tool_call",   "tool": "run_tabpfn", "input": {...} }
{ "type": "tool_result", "tool": "run_tabpfn", "output": {...} }
{ "type": "prediction",  "regime": "...", "confidence": 0.82 }
{ "type": "done",        "summary": "..." }
```

**Testing**: pytest with `asyncio_mode = "auto"`. `conftest.py` provides a `TestClient(app)` fixture.

### Frontend (`frontend/`)

Next.js 15 App Router, TypeScript, Tailwind CSS, shadcn/ui (Radix UI primitives), Recharts, Framer Motion, Zustand for state.

- `lib/api.ts` — typed fetch wrapper; base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`); 30 s abort timeout
- `lib/websocket.ts` — `useRunStream(runId)` hook; base URL from `NEXT_PUBLIC_WS_URL` (default `ws://localhost:8000`); caps message history at 200
- `app/page.tsx` — placeholder home page; `RegimeDashboard`, `AgentStream`, `DerivativesPanel` components are not yet built

**Testing**: Vitest + `@testing-library/react` + jsdom. Tests live in `lib/__tests__/`.

### Infrastructure

- **PostgreSQL** (default: `signalyst:signalyst@localhost:5432/signalyst`) + **Redis** (`:6379`) — both provided by `docker-compose.yml`
- **Alembic** migrations in `backend/alembic/`; `alembic.ini` hardcodes dev DB URL (override via `DATABASE_URL` env var in production)
- **CI**: GitHub Actions (`.github/`); release automation via `release-please`; security scanning and Codecov configured
- **Pre-commit**: ruff + mypy (`.pre-commit-config.yaml`)

### Environment variables

See `.env.example`. Required for live data: `ANTHROPIC_API_KEY`, `FRED_API_KEY`. Tests run without any secrets set.

## Behavioral Guidelines

Derived from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills). These guidelines bias toward caution over speed — use judgment for trivial tasks.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 5. Plan Implementation & Git Discipline

**Complete the full plan before pushing. CI must pass before a PR is created.**

When executing a superpowers plan:
- `git add` and `git commit` freely as each step completes — no need to ask for confirmation.
- Do not `git push` until every step in the plan is fully implemented and verified locally.
- When the plan is complete, check with the user before pushing.

After every `git push` (whether creating a PR or pushing follow-up commits):
- Check CI immediately with `gh pr checks` (if a PR exists) or `gh run list --branch <branch>`.
- Wait for all checks to complete — do not report the task as done while CI is still running.
- If any check fails, read the logs with `gh run view <run-id> --log-failed`, fix the root cause, and push again.
- Do not leave a PR open with failing CI — fix it before moving on.
