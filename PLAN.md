# TemporalAgent — Project Plan

An agentic analytics system that detects oil market regime shifts using macro, geopolitical, and energy-specific signals — bridging time series and tabular data with TabPFN as the inference backbone and an LLM agent as the reasoning orchestrator.

## Core Concept

Most real-world prediction problems have both a temporal dimension (things change over time) and a cross-sectional dimension (entities differ). TemporalAgent handles both — featurizing time series into tabular snapshots for TabPFN, orchestrated by an agent that decides what to look at, explains what it finds, and iterates.

**Key TabPFN advantage exploited**: In-context learning means no retraining. When new data arrives, just update the context window — a genuine architectural advantage over tree models for streaming/online scenarios.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        LLM Agent                            │
│   (orchestrates tools, reasons about features, explains)    │
└────────┬──────────────┬──────────────┬──────────────────────┘
         │              │              │
    fetch_data    engineer_features   explain
    run_tabpfn    backtest            detect_drift
         │              │              │
┌────────▼──────────────▼──────────────▼──────────────────────┐
│              TimeSeriesFeaturizer                            │
│  rolling stats │ lag features │ momentum │ regime features   │
└────────────────────────────────┬─────────────────────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │         Tabular Feature Matrix       │
              │  (time series features + static      │
              │   metadata, text embeddings, etc.)   │
              └──────────────────┬──────────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │    TabPFN Inference Engine           │
              │  Classifier (regime/event)           │
              │  Regressor (value/score)             │
              │  Uncertainty quantification          │
              └─────────────────────────────────────┘
```

---

## Implementation Status

| Session | Focus | Status |
|---|---|---|
| Session 1 | Data connectors (yfinance, FRED, EIA) + `TimeSeriesFeaturizer` | ✅ Done — PR #43 |
| Session 2 | `OilRegimeClassifier` + `DirectionClassifier` (tabpfn-client) | ✅ Done — PR #45 |
| Session 3 | `src/db/` — SQLModel run/history models + Alembic migration | ✅ Done — PR #51 |
| Session 4 | `src/agent/` — tool registry + 4 core tools + ReAct loop (OpenAI SDK) | ✅ Done — PR #56 |
| Session 5 | Wire up API routes (replace 501s) + WebSocket Redis pub/sub + deferred tools (`detect_drift`, `backtest`, `evaluate_features`, `fetch_geopolitical_risk`) | ✅ Done — PR #56 |
| Session 6 | Frontend core — split-pane layout, AgentStream, RegimeCard, DirectionCard, SummaryPanel | ✅ Done — PR #58 |
| Session 7 | Frontend UX — collapsible agent drawer, live thought stream, tab navigation, fix evaluate_features crash | ✅ Done — PR #71 |

See `docs/BACKLOG.md` for known issues and deferred improvements.

---

## Components

### 1. `TimeSeriesFeaturizer`
Transforms raw time series into tabular snapshots.
- Rolling statistics: mean, std, min/max, skewness over multiple windows (5d, 20d, 60d)
- Lag features: t-1, t-5, t-20
- Momentum and rate-of-change
- Energy-specific regime features: inventory trend slope, rig count momentum, GPR level
- Enforces temporal ordering — no data leakage

### 2. TabPFN Inference Engine
Wraps `TabPFNClassifier` and `TabPFNRegressor` from the TabPFN library.
- Regime classifier: bull supercycle / range-bound / bust / geopolitical spike
- WTI price direction predictor: up/down next 4 weeks
- Energy equity outperformance predictor: XLE vs SPY next quarter
- Uncertainty quantification via ensemble diversity

### 3. LLM Agent
Orchestrates the full pipeline with tool use.

**Tools (Session 4 — core):**
- `fetch_data(tickers, fred_series, start, end)` — pulls from yfinance + FRED
- `engineer_features(windows, lags)` — calls TimeSeriesFeaturizer
- `run_tabpfn(task, horizon)` — regime classification or direction prediction
- `explain_prediction(regime, direction, confidence, key_features)` — natural language explanation

**Tools (Session 5 — deferred):**
- `evaluate_features(feature_importances)` — SHAP-based analysis via tabpfn-extensions
- `detect_drift(recent_data, historical_data)` — flags distribution shift
- `backtest(strategy, date_range)` — walk-forward evaluation
- `fetch_geopolitical_risk(date_range)` — pulls GPR index from Fed

**Agent loop (ReAct-style):**
```
Observe → Think → Act → Observe → ...
```

Agent iterates: tries feature set → evaluates → refines → explains

### 4. Temporal Evaluation Framework
Walk-forward cross-validation — no future data leaks into training context.
- Backtesting with Sharpe ratio, regime accuracy metrics
- Comparison vs. baselines (XGBoost, simple momentum)
- Uncertainty calibration plots

### 5. Authentication

JWT-based auth on the backend, NextAuth.js on the frontend. Dependencies are already installed (`python-jose`, `passlib[bcrypt]`, `next-auth`); the implementation is planned for the Mid tier.

**Backend**
- User model in PostgreSQL (SQLModel)
- `POST /api/auth/register` — hashed password via `passlib[bcrypt]`
- `POST /api/auth/token` — OAuth2 password flow, returns short-lived JWT access token
- `JWT_SECRET` + `SECRET_KEY` added back to `Settings` when this is wired up
- FastAPI `Depends(get_current_user)` dependency guards all non-public routes
- Run history is scoped per user — `GET /api/history` returns only the authenticated user's runs

**Frontend**
- NextAuth.js with a Credentials provider backed by `POST /api/auth/token`
- `useSession()` hook gates the dashboard; unauthenticated users are redirected to `/login`
- API client attaches `Authorization: Bearer <token>` on every request
- OAuth providers (GitHub, Google) can be added later by configuring NextAuth.js — no backend changes needed

---

## Domain: Energy / Oil & Gas Market Intelligence

**Why:** Driven by a small, well-defined set of signals that map cleanly to tabular features. Regime shifts are historically distinct and well-labeled. Geopolitical risk (Russia-Ukraine, Middle East) is the unique angle most quant models ignore — directly quantifiable via the Fed's free Geopolitical Risk Index. Highly relevant and easy to explain to any interviewer.

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

## Future Extension: Image Data (Phase 2)

Adding satellite imagery as an additional signal source — a natural next step once the core pipeline is stable:

- **Oil storage tank fill levels** — satellite images of floating-roof tanks; shadow angle reveals inventory volume. Provides independent cross-check against EIA reports.
- **Refinery activity** — thermal/optical imagery of refinery flare stacks and facility activity
- **Shipping traffic** — satellite AIS + imagery of tanker congestion at key chokepoints (Strait of Hormuz, Suez)

**Pipeline addition:**
```
Satellite image → vision encoder (e.g. DINOv2) → embedding vector
                                                          ↓
                                    Concatenate with tabular features
                                                          ↓
                                              TabPFN (unchanged)
```

This keeps TabPFN as the unchanged inference engine — images just become additional numerical columns after embedding, requiring PCA or feature selection to stay within the 2000-feature limit.

---

## Key Technical Differentiator

Agent-driven iterative feature refinement:

```python
for iteration in range(max_iterations):
    features = engineer_features(data, current_config)
    cv_score = temporal_cross_validate(tabpfn, features, labels)

    if cv_score > threshold:
        break

    next_config = agent.reason(
        current_score=cv_score,
        feature_importances=get_shap_values(tabpfn, features),
        data_characteristics=describe_data(data),
    )
    current_config = next_config
```

---

## Repo Structure

Single monorepo:

```
temporal-agent/
├── backend/           # Python — FastAPI, agent logic, TabPFN inference, data pipelines
│   ├── src/
│   │   ├── agent/         # LLM agent, tools, ReAct loop
│   │   ├── featurizer/    # TimeSeriesFeaturizer
│   │   ├── inference/     # TabPFN wrappers (OilRegimeClassifier, DirectionClassifier)
│   │   ├── data/          # FRED, yfinance, EIA connectors
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
    ├── lib/               # API client, WebSocket hook
    └── package.json
```

### API Contract (backend → frontend)

**REST:**
- `POST /analyze` — trigger a full analysis run, returns `run_id`
- `GET /runs/{run_id}` — fetch completed run results
- `GET /history` — past analyses

**WebSocket:**
- `WS /runs/{run_id}/stream` — streams agent steps in real time

```json
// Stream message format
{ "type": "thought",      "content": "Classifying current macro regime..." }
{ "type": "tool_call",    "tool": "run_tabpfn", "input": { ... } }
{ "type": "tool_result",  "tool": "run_tabpfn", "output": { ... } }
{ "type": "prediction",   "regime": "slowdown", "confidence": 0.82 }
{ "type": "done",         "summary": "..." }
```

WebSocket streaming is important here — the agent's ReAct loop is iterative and can take several seconds. Streaming each step to the UI makes the reasoning transparent and the UX feel alive.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Agent framework | OpenAI SDK (gpt-5.5 / gpt-5.5-mini) with tool use |
| TabPFN | `tabpfn-client` (cloud API) + `tabpfn-extensions` (SHAP) |
| Time series features | `tsfresh` or manual + `pandas` |
| Data | `fredapi`, `yfinance`, EIA API |
| Eval | Custom walk-forward backtest + `scikit-learn` |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js (React) |
| UI components | shadcn/ui + Recharts / Tremor for charts |

---

## Phase 2: Derivatives Exposure Visualization

Once the core regime prediction pipeline is stable, the regime output becomes the **input** to a derivatives pricing module. This is the "action layer" on top of TabPFN — what a trader actually does with the regime signal.

### The Bridge

```
TabPFN regime classification
        ↓
Vol regime lookup (historical realized vol per regime)
e.g. geopolitical spike → σ ≈ 45%, range-bound → σ ≈ 22%
        ↓
Stochastic valuation model
        ↓
Monte Carlo path simulation
        ↓
European / American call pricing + visualization
```

The agent surfaces this naturally:
> "Current regime: geopolitical spike. Historical 30-day realized vol in this regime: 45%. Here is what a WTI 1-month call at strike $85 looks like under these conditions."

### Stochastic Models

| Model | When to use |
|---|---|
| **GBM** (Geometric Brownian Motion) | Baseline, simple, good for European calls |
| **Heston** (stochastic volatility) | More realistic for energy — vol is not constant |

### Simulation Output

- **N simulated WTI price paths** over option tenor
- **European call price**: `E[max(S_T - K, 0)]` discounted
- **American call price**: Longstaff-Schwartz or binomial tree (early exercise premium)
- **Greeks**: delta, gamma, vega, theta

### UI Components (additions to `temporal-agent-ui`)

```
components/
├── DerivativesPanel/
│   ├── PathFanChart/        # Animated Monte Carlo paths (fan chart)
│   ├── PayoffSurface/       # 3D payoff vs. price vs. time
│   ├── GreeksDashboard/     # Delta, gamma, vega, theta gauges
│   └── EuroVsAmericanCard/  # Side-by-side price + early exercise premium
```

### Backend additions (`temporal-agent`)

```
src/
├── derivatives/
│   ├── models.py        # GBM, Heston simulation
│   ├── pricing.py       # European (analytical + MC), American (LSM)
│   └── greeks.py        # Numerical Greeks via finite difference
```

### New API endpoint

```
POST /derivatives/price
{
  "regime": "geopolitical_spike",
  "spot": 87.5,
  "strike": 90.0,
  "tenor_days": 30,
  "option_type": "call",
  "style": "european" | "american",
  "n_paths": 10000
}
```

### Tech additions

| Layer | Tool |
|---|---|
| Stochastic simulation | `numpy` (GBM), `quantlib-python` or custom (Heston/LSM) |
| 3D visualization | Three.js or Plotly (via API response) |
| Animated paths | Framer Motion or D3.js |

---

## Scope Tiers

| Tier | Scope | Timeframe |
|---|---|---|
| **MVP** | FastAPI backend, single-agent, oil regime classification, basic Next.js UI | 2–3 weeks |
| **Mid** | Multi-tool agent, WTI direction + XLE prediction, backtesting, WebSocket streaming, full dashboard | 4–6 weeks |
| **Full** | Multi-agent, geopolitical spike detection, derivatives panel (Phase 2), satellite image embeddings (Phase 2), polished UI | 8–12 weeks |

---

## What This Demonstrates

| Skill | How |
|---|---|
| Software engineering | Modular architecture, clean APIs, data pipeline, temporal split discipline |
| Agent development | Multi-step tool use, ReAct loop, reflection, explanation generation |
| Tabular data | Feature modality handling, dimensionality management, TabPFN ensemble configs |
| Time series | Temporal featurization, leakage prevention, regime awareness, walk-forward eval |
| Quant finance | Stochastic vol models, Monte Carlo simulation, options pricing, Greeks |

---

## User Flow

### Step 1 — Home Page
User opens the app and sees:
- Current energy market overview (latest data timestamp)
- Summary of last analysis (if any)
- A prominent "Start Analysis" button

### Step 2 — Configure Analysis
User clicks "Start Analysis" and sets:
- **Time range**: historical data window (e.g. past 5 years)
- **Prediction targets**: regime classification / WTI price direction / XLE outperformance / or all
- **Advanced options** (collapsible): feature window sizes, ensemble count, enable anomaly detection

### Step 3 — Agent Reasoning Stream (core experience)
User clicks "Run". The page switches to a real-time streaming view with two columns:

**Left — Agent Thought Stream** (WebSocket, live)
```
🔍 Fetching EIA inventory data and FRED macro series...
⚙️  Tool call: engineer_features (windows: 20d, 60d)
🧠 Feature set score: 0.71 — adding yield curve slope feature...
⚙️  Tool call: run_tabpfn (classification)
📊 Regime: Geopolitical Spike (confidence 82%)
⚙️  Tool call: run_tabpfn (regression — WTI direction)
💡 WTI likely up next 4 weeks. XLE expected to outperform SPY.
✅ Analysis complete
```

**Right — Results Rendered Live**
- Regime card (appears as soon as classified)
- WTI price direction indicator
- Confidence bars filling in progressively

### Step 4 — Full Dashboard
Once complete, the full dashboard renders:
- **Regime card**: current regime + historical regime timeline
- **WTI direction card**: predicted direction + confidence interval
- **Geopolitical Risk chart**: GPR index overlay on WTI price
- **Feature importance chart**: SHAP values — which signals drove the prediction
- **Backtest chart**: walk-forward strategy performance vs. SPY benchmark
- **Agent analysis report**: natural language summary of the full reasoning chain

### Step 5 — Derivatives Panel (Phase 2)
Below the main dashboard, a "Derivatives Exposure" panel:
- User inputs: spot price, strike, tenor, option style (European / American)
- Regime auto-fills the vol assumption
- Panel renders:
  - Animated Monte Carlo path fan chart
  - Payoff surface (price vs. time)
  - Greeks dashboard (delta, gamma, vega, theta)
  - European vs. American side-by-side comparison

### Step 6 — Follow-up Questions
User can type follow-up questions in a chat box below the report:
- "Why is energy expected to outperform?"
- "What if the GPR index rises another 10 points?"
- "Show me how the model performed during the 2022 war spike"

Agent calls the relevant tools and streams back the answer.

### Step 7 — Save & Export
- Analysis saved to history (accessible from home page)
- Export as PDF report or CSV data
- Shareable read-only link

---

## Manual Setup Steps (Post-Scaffold)

The following cannot be automated and require manual action:

### First-time setup
- [ ] Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`, `FRED_API_KEY`
- [ ] Run `make install` to install backend (`uv sync`) and frontend (`npm install`) dependencies
- [ ] Run `npx shadcn@latest init` inside `frontend/` to initialize shadcn/ui component library
- [ ] Run `make migrate` once PostgreSQL is running to apply database migrations

### CI/CD secrets (GitHub)
Add these in **Settings → Secrets → Actions** on the GitHub repo:
- [ ] `ANTHROPIC_API_KEY`
- [ ] `FRED_API_KEY`
- [ ] `SENTRY_DSN`

### Observability
- [ ] Create a [Sentry](https://sentry.io) project, copy the DSN to `.env` and GitHub secrets
- [ ] (Optional) Set up Prometheus + Grafana for metrics — add `prometheus-fastapi-instrumentator` to backend

### Auth providers
- [ ] Configure NextAuth.js providers in `frontend/app/api/auth/[...nextauth]/route.ts` (GitHub OAuth, Google OAuth, or credentials)
- [ ] Add OAuth app credentials to `.env`

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
