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

TemporalAgent detects oil market regime shifts using macro, geopolitical, and energy signals. The core loop: fetch time-series data → featurize into tabular snapshots → classify regime and predict price direction with TabPFN → stream the LLM agent's ReAct reasoning to the frontend over WebSocket.

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

- **PostgreSQL** (default: `temporal:temporal@localhost:5432/temporal_agent`) + **Redis** (`:6379`) — both provided by `docker-compose.yml`
- **Alembic** migrations in `backend/alembic/`; `alembic.ini` hardcodes dev DB URL (override via `DATABASE_URL` env var in production)
- **CI**: GitHub Actions (`.github/`); release automation via `release-please`; security scanning and Codecov configured
- **Pre-commit**: ruff + mypy (`.pre-commit-config.yaml`)

### Environment variables

See `.env.example`. Required for live data: `ANTHROPIC_API_KEY`, `FRED_API_KEY`. Tests run without any secrets set.
