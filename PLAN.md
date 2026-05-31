# Signalyst — Project Plan

An agentic analytics system that detects market regime shifts using macro, geopolitical, and energy-specific signals — bridging time series and tabular data with TabPFN as the inference backbone and a multi-agent pipeline as the reasoning orchestrator.

## Core Concept

Most real-world prediction problems have both a temporal dimension (things change over time) and a cross-sectional dimension (entities differ). Signalyst handles both — featurizing time series into tabular snapshots for TabPFN, orchestrated by a multi-agent pipeline that decides what data to fetch, explains what it finds, and iterates with the user.

**Key TabPFN advantage exploited**: In-context learning means no retraining. When new data arrives, just update the context window — a genuine architectural advantage over tree models for streaming/online scenarios.

For the current backend architecture, agent definitions, session data model, API design, and PR breakdown see:
**[`docs/backend-redesign.md`](docs/backend-redesign.md)**

---

## Domain: Energy / Oil & Gas Market Intelligence

**Why:** Driven by a small, well-defined set of signals that map cleanly to tabular features. Regime shifts are historically distinct and well-labeled. Geopolitical risk (Russia-Ukraine, Middle East) is the unique angle most quant models ignore — directly quantifiable via the Fed's free Geopolitical Risk Index. Highly relevant and easy to explain to any interviewer.

Oil is the **primary market profile** — fully built out with all connectors, featurizer configs, and regime labels. The architecture supports other asset classes (equities, FX) via additional market profiles.

### Data Sources

| Signal | Type | Source |
|---|---|---|
| WTI / Brent crude price | Time series | `yfinance` |
| EIA weekly inventory builds | Time series | EIA API (free) |
| Baker Hughes rig count | Time series | `yfinance` / BH website |
| OPEC production quota changes | Tabular event | manual / news |
| US dollar index (DXY) | Time series | `yfinance` |
| Global PMI / industrial demand | Time series | `fredapi` |
| Geopolitical Risk Index (GPR) | Time series | Federal Reserve (free) |
| Refinery utilization rate | Time series | EIA API (free) |

### Prediction Tasks
1. **Regime classification**: bull supercycle / range-bound / bust / geopolitical spike
2. **WTI price direction**: up/down over next 4 weeks
3. **Energy equity outperformance**: will XLE beat SPY next quarter?

### Agent Reasoning Example
> "Rig count is falling while inventory builds are rising → supply response lagging → regime likely transitioning from contraction to early recovery → historically XLE and OIH outperform in this phase → confidence 78%"

### Historical Regimes (training labels)
- **Supercycle**: 2021–2022 (post-COVID demand + Russia-Ukraine war spike)
- **Bust**: 2014–2016 (shale glut), 2020 (COVID demand collapse)
- **Geopolitical spike**: 2022 Feb–Mar (Russia invasion), 2024 Middle East escalation
- **Range-bound**: 2017–2019, 2023

---

## Repo Structure

```
signalyst/
├── backend/           # Python — FastAPI, multi-agent pipeline, TabPFN inference, data pipelines
│   ├── src/
│   │   ├── agent/         # Agents: DataSourceDiscovery, Data, Explanation, FollowUp, ConnectorBuilder
│   │   ├── services/      # Deterministic services: FeaturizerService, TabPFNService
│   │   ├── featurizer/    # TimeSeriesFeaturizer
│   │   ├── inference/     # TabPFN wrappers (OilRegimeClassifier, DirectionClassifier)
│   │   ├── data/          # FRED, yfinance, EIA connectors + connector registry
│   │   └── eval/          # Walk-forward backtest
│   ├── api/               # FastAPI routes + WebSocket handlers
│   ├── scripts/           # demo.py — end-to-end pipeline demo
│   ├── tests/
│   └── pyproject.toml
└── frontend/          # Next.js — dashboard UI
    ├── app/               # Next.js app router pages
    ├── components/
    │   ├── RegimeDashboard/       # Oil market regime display
    │   ├── PriceDirectionCard/    # WTI/Brent prediction
    │   ├── GeopoliticalRiskChart/ # GPR index overlay
    │   ├── AgentStream/           # Live agent thought stream
    │   ├── FeatureImportance/     # SHAP chart
    │   └── BacktestChart/         # Walk-forward performance
    ├── lib/               # API client, WebSocket hook, Zustand store
    └── package.json
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Agent framework | OpenAI SDK (GPT) with tool use |
| TabPFN | `tabpfn-client` (cloud API) + `tabpfn-extensions` (SHAP) |
| Time series features | Manual + `pandas` |
| Data | `fredapi`, `yfinance`, EIA API |
| Eval | Custom walk-forward backtest + `scikit-learn` |
| Backend | FastAPI + BackgroundTasks + Redis pub/sub + WebSocket |
| Database | PostgreSQL via SQLModel + asyncpg |
| Frontend | Next.js 15 (React) |
| UI components | shadcn/ui + Recharts for charts |

---

## Phase 2: Derivatives Exposure Visualization

Once the core regime prediction pipeline is stable, the regime output becomes the **input** to a derivatives pricing module — the "action layer" on top of TabPFN showing what a trader actually does with the regime signal.

```
TabPFN regime classification
        ↓
Vol regime lookup (historical realized vol per regime)
e.g. geopolitical spike → σ ≈ 45%, range-bound → σ ≈ 22%
        ↓
Stochastic valuation model (GBM / Heston)
        ↓
Monte Carlo path simulation
        ↓
European / American call pricing + Greeks + visualization
```

The agent surfaces this naturally:
> "Current regime: geopolitical spike. Historical 30-day realized vol in this regime: 45%. Here is what a WTI 1-month call at strike $85 looks like under these conditions."

**UI additions:**
```
components/
├── DerivativesPanel/
│   ├── PathFanChart/        # Animated Monte Carlo paths
│   ├── PayoffSurface/       # 3D payoff vs. price vs. time
│   ├── GreeksDashboard/     # Delta, gamma, vega, theta
│   └── EuroVsAmericanCard/  # Side-by-side + early exercise premium
```

**New API endpoint:** `POST /api/derivatives/price`

---

## Phase 2: Satellite Imagery Signals

Adding satellite imagery as an additional data source once the core pipeline is stable:

- **Oil storage tank fill levels** — floating-roof tank shadow angles reveal inventory volume; cross-check against EIA reports
- **Refinery activity** — thermal/optical imagery of flare stacks and facility activity
- **Shipping traffic** — tanker congestion at Strait of Hormuz, Suez Canal

Images feed into TabPFN unchanged via a vision encoder:
```
Satellite image → DINOv2 encoder → embedding vector
                                          ↓
                      Concatenate with tabular features → TabPFN
```

---

## Scope Tiers

| Tier | Scope |
|---|---|
| **Backend redesign** | Session model, multi-agent pipeline, deterministic services, artifact cache, market profiles — see redesign spec (7 PRs) |
| **Mid** | Authentication (JWT + NextAuth.js), WebSocket Redis pub/sub scaling, history page |
| **Full** | Derivatives panel (Phase 2), satellite image embeddings (Phase 2), ConnectorBuilderAgent, polished UI |

---

## What This Demonstrates

| Skill | How |
|---|---|
| Software engineering | Modular architecture, clean APIs, staged pipeline, temporal split discipline |
| Agent development | Multi-agent design, staged LLM reasoning, deterministic services, tool use |
| Tabular data | Feature modality handling, dimensionality management, TabPFN ensemble configs |
| Time series | Temporal featurization, leakage prevention, regime awareness, walk-forward eval |
| Quant finance | Stochastic vol models, Monte Carlo simulation, options pricing, Greeks |

---

## Manual Setup Steps

The following cannot be automated and require manual action:

### First-time setup
- [ ] Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`, `FRED_API_KEY`
- [ ] Run `make install` to install backend (`uv sync`) and frontend (`npm install`) dependencies
- [ ] Run `npx shadcn@latest init` inside `frontend/` to initialize shadcn/ui component library
- [ ] Run `make migrate` once PostgreSQL is running to apply database migrations

### CI/CD secrets (GitHub)
Add these in **Settings → Secrets → Actions** on the GitHub repo:
- [ ] `OPENAI_API_KEY`
- [ ] `FRED_API_KEY`
- [ ] `SENTRY_DSN`

### Observability
- [ ] Create a [Sentry](https://sentry.io) project, copy the DSN to `.env` and GitHub secrets
- [ ] (Optional) Set up Prometheus + Grafana for metrics — add `prometheus-fastapi-instrumentator` to backend

### Cloud deployment
- [ ] **Frontend**: Deploy to [Vercel](https://vercel.com) — connect GitHub repo, set `NEXT_PUBLIC_API_URL` env var
- [ ] **Backend**: Deploy to [Railway](https://railway.app) or [Render](https://render.com) — provision PostgreSQL + Redis add-ons
- [ ] Update CORS `allow_origins` in `backend/api/main.py` to production frontend URL

### Monitoring (production)
- [ ] Set up log aggregation (Datadog, Logtail, or Axiom)
- [ ] Configure uptime monitoring (Better Uptime, Checkly)
- [ ] Set up database backups on Railway/Render

---

## Inspiration / Related Work

- [TabPFN (PriorLabs)](https://github.com/PriorLabs/TabPFN) — core inference engine
- [tabpfn-extensions](https://github.com/priorlabs/tabpfn-extensions) — SHAP, embeddings, HPO
- [HUPD](https://patentdataset.org/) — alternative domain (patent grant prediction)
- [tsfresh](https://tsfresh.readthedocs.io/) — automated time series feature extraction
