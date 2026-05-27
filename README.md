# TemporalAgent

An agentic analytics system that detects oil market regime shifts using macro, geopolitical, and energy-specific signals — powered by [TabPFN](https://github.com/PriorLabs/TabPFN) and an LLM agent.

## What it does

1. Pulls energy market data (WTI/Brent, EIA inventories, rig count, geopolitical risk index)
2. Featurizes time series into tabular snapshots
3. Uses TabPFN to classify the current market regime and predict price direction
4. Streams the agent's reasoning to the UI in real time
5. Visualizes derivatives exposure (Monte Carlo paths, Greeks) based on the predicted regime

## Stack

| Layer | Tool |
|---|---|
| Backend | Python 3.12, FastAPI, TabPFN, Anthropic API |
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui |
| Database | PostgreSQL + Redis |
| Infra | Docker, GitHub Actions |

## Getting started

```bash
# 1. Install dependencies
make install

# 2. Copy and fill in env vars
cp .env.example .env

# 3. Start everything
docker-compose up

# 4. Run database migrations
make migrate
```

Backend runs on `http://localhost:8000`, frontend on `http://localhost:3000`.

## Development

Run the app servers directly with `uv`/`npm` for the fastest experience — HMR and hot reload are noticeably slower through Docker volume mounts. Use Docker only for the databases.

```bash
# Start databases (Postgres + Redis)
docker-compose up postgres redis

# In separate terminals:
make dev-backend    # FastAPI with hot reload on :8000
make dev-frontend   # Next.js dev server on :3000

make test           # Run all tests
make lint           # Ruff + mypy + ESLint
```

To inspect the database, connect [TablePlus](https://tableplus.com) (or any PostgreSQL client) to `localhost:5432`, user `temporal`, password `temporal`, database `temporal_agent`.

## Project structure

```
temporal-agent/
├── backend/        # FastAPI + TabPFN + agent logic
├── frontend/       # Next.js dashboard
├── docker-compose.yml
└── Makefile
```

See [PLAN.md](./PLAN.md) for the full architecture and roadmap.
