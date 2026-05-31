# Backend Redesign — Design Spec

**Date:** 2026-05-31
**Branch:** feat/agent-redesign
**Status:** Design only — no implementation on this branch

---

## Overview

Signalyst is a multi-agent financial analytics system. The current backend has a monolithic ReAct loop that conflates deterministic data work with LLM reasoning. This redesign separates concerns clearly: LLM agents run only where reasoning is needed; featurizing and TabPFN inference are deterministic services. A persistent session is the single source of truth across all stages.

The system supports any market (oil, equities, FX) via a **market profile** abstraction. Oil remains the primary, fully-built-out profile. The architecture is general enough to add new profiles without touching core logic.

---

## User Flow

### Step 1 — Home Page

User sees a list of past sessions with: market profile, timeframe, current stage, last updated timestamp. A "New Analysis" button opens the session creation form.

### Step 2 — Create Session

User selects:
- **Market profile** — dropdown populated from `GET /api/profiles` (e.g. Oil Markets, S&P 500, EUR/USD)
- **Timeframe** — start and end dates
- **Auto mode** — toggle to skip the USER_REVIEW gate and run all stages automatically

User clicks **Start**. `POST /api/sessions` returns `202` with a `session_id`. Frontend immediately connects to `WS /ws/sessions/{id}/stream`.

### Step 3 — Data Source Discovery

`DataSourceDiscoveryAgent` runs in the background. It recommends data sources based on the market profile, explores novel sources if needed using HTTP primitives, and streams its reasoning to the frontend.

Example stream:
```
"For oil market analysis I recommend:
  ✓ WTI/Brent crude prices (yfinance — available)
  ✓ EIA weekly inventory builds (EIA API — available)
  ✓ Geopolitical Risk Index (Federal Reserve — available)
  ✓ Baker Hughes rig count (yfinance — available)
  ✓ US Dollar Index DXY (yfinance — available)
  ? OPEC meeting minutes — no structured API, suggest upload
  + Found IMF Primary Commodity Prices dataset — want me to connect?"
```

### Step 4 — Data Gathering

`DataAgent` fetches the approved sources using built-in connectors and the connector registry. It streams each tool call and result. On completion it writes a `DataArtifact` to the session and the stage transitions to `USER_REVIEW`.

### Step 5 — User Review Gate

*(Skipped in auto mode)*

Frontend renders a data dashboard from `DataArtifact.data_manifest` — coverage, shape, summary stats, and visualisations of the raw time series.

The user has three options:

| Action | Endpoint | What happens |
|---|---|---|
| Clicks "Run Analysis" | `POST /proceed` | Stage → FEATURIZING, no LLM call |
| Types "add Baker Hughes data" | `POST /chat` | ReviewInterpreter → refetch → back to DATA_GATHERING |
| Types "focus on momentum, use 30d windows" | `POST /chat` | ReviewInterpreter → patches `featurizer_config` → stage → FEATURIZING |

### Step 6 — Featurizing

`FeaturizerService` (deterministic). Reads `DataArtifact.raw_data` and `Session.featurizer_config`. Checks the within-session and cross-session cache before running. Writes a `FeatureArtifact`.

### Step 7 — Analyzing

`TabPFNService` (deterministic). Reads `FeatureArtifact`. Checks cache. Runs regime classification, direction prediction, SHAP feature importance, drift detection, and walk-forward backtest. Writes an `AnalysisResult` (TabPFN fields only — `summary` is null at this point).

### Step 8 — Explaining

`ExplanationAgent` (LLM, no tools). Reads the full session: `AnalysisResult`, `data_manifest`, `featurizer_config`, and the full conversation history. Streams a natural language explanation to the frontend. Writes `AnalysisResult.summary` on completion.

### Step 9 — Follow-Up

Frontend renders the full dashboard: regime card, direction card, GPR chart, SHAP feature importance chart, backtest chart, and the agent's summary.

User can ask follow-up questions via `POST /chat`. `FollowUpAgent` answers using the full session context and can trigger stage regression:

| User says | Agent action |
|---|---|
| "Why is drift elevated?" | Answers from session context |
| "Re-run with 60d windows" | Patches `featurizer_config` → `POST /rerun { stage: FEATURIZING }` |
| "Fetch refinery utilisation data too" | `POST /rerun { stage: DATA_GATHERING }` with new source |
| "Compare to my last session" | Pulls prior session artifacts for comparison |

### Step 10 — New Session with Same Config

User clicks **New Analysis** and enters the same market profile and timeframe. `POST /api/sessions` fires. Before each stage runs, the backend checks the global artifact cache. On a hit, the existing artifact is copied into the new session with provenance metadata. The WebSocket stream shows cache indicators:

```
"Using data from session #4 (2026-05-15) · Cached"
"Using TabPFN results from session #4 · Cached"
```

`ExplanationAgent` always re-runs — it is cheap and the user's framing may differ.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                        │
│                                                             │
│  REST endpoints ──► Background Tasks ──► Redis pub/sub      │
│                           │                    │            │
│                    Agent / Service        WebSocket         │
│                      execution            forwarding        │
└─────────────────────────────────────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
         PostgreSQL       Redis        OpenAI API
        (SQLModel)     (pub/sub)      (GPT agents)
```

### Background Task Pattern

Every endpoint that triggers agent work returns `202 Accepted` immediately. The agent runs in a FastAPI `BackgroundTask` and publishes progress to a Redis channel. The WebSocket handler forwards messages from that channel to the connected frontend client.

```
POST /api/sessions/{id}/proceed
  → validate + update session.stage in DB
  → return 202
  → background_tasks.add_task(run_featurizer_service, session_id)

FeaturizerService (background):
  → read session from DB
  → check cache
  → run TimeSeriesFeaturizer
  → publish progress to redis channel "session:{id}"
  → write FeatureArtifact to DB
  → publish stage_transition event
```

---

## Pipeline

```
CONFIGURING
    │  POST /api/sessions → DataSourceDiscoveryAgent starts in background
    ▼
DATA_GATHERING    ← DataAgent (LLM + tools)
    │  DataAgent completes → stage auto-transitions
    ▼
USER_REVIEW       ← user gate (skipped in auto mode)
    │
    ├── POST /proceed            → FEATURIZING
    ├── POST /chat "add X"       → ReviewInterpreter → DATA_GATHERING
    └── POST /chat "focus on Y"  → ReviewInterpreter → patch featurizer_config → FEATURIZING
    ▼
FEATURIZING       ← FeaturizerService (deterministic)
    │  completes → auto-transition
    ▼
ANALYZING         ← TabPFNService (deterministic)
    │  completes → auto-transition
    ▼
EXPLAINING        ← ExplanationAgent (LLM, no tools)
    │  completes → auto-transition
    ▼
FOLLOW_UP         ← FollowUpAgent (LLM + tools)
    │
    └── POST /chat → answers / triggers reruns
        POST /rerun { stage } → regression to any prior stage
```

---

## Database Models

### Session

```python
class SessionStage(str, Enum):
    CONFIGURING    = "configuring"
    DATA_GATHERING = "data_gathering"
    USER_REVIEW    = "user_review"
    FEATURIZING    = "featurizing"
    ANALYZING      = "analyzing"
    EXPLAINING     = "explaining"
    FOLLOW_UP      = "follow_up"

class SessionStatus(str, Enum):
    RUNNING  = "running"   # a background task is actively executing
    WAITING  = "waiting"   # at a user gate (USER_REVIEW, FOLLOW_UP) or idle
    FAILED   = "failed"    # background task crashed — see session.error
    CANCELED = "canceled"  # user canceled via POST /cancel

class Session(SQLModel, table=True):
    id:                UUID       # primary key
    market_profile:    str        # "oil" | "sp500" | "eurusd" | ...
    timeframe_start:   date
    timeframe_end:     date
    stage:             SessionStage  = CONFIGURING
    status:            SessionStatus = WAITING
    error:             str | None    = None    # set when status = FAILED
    auto:              bool          = False   # skip USER_REVIEW gate
    featurizer_config: JSON          = {}      # mutable; patched by ReviewInterpreter / FollowUpAgent
    pending_sources:   JSON          = []      # DataSource[] written by DataSourceDiscoveryAgent,
                                               # read by DataAgent — cleared after DATA_GATHERING
    conversation:      JSON          = []      # ChatMessage[] — append-only, full history
    stage_history:     JSON          = []      # [{ stage, entered_at }] — append-only, set by transition_stage()
    created_at:        datetime
    updated_at:        datetime
```

`stage` tracks *where* in the pipeline the session is. `status` tracks *what it is doing* at that stage. Together they give the full picture:

| stage | status | Meaning |
|---|---|---|
| DATA_GATHERING | RUNNING | DataAgent is fetching data |
| USER_REVIEW | WAITING | Waiting for user to proceed or chat |
| FEATURIZING | RUNNING | FeaturizerService is computing |
| DATA_GATHERING | FAILED | DataAgent crashed — see `error` |
| FOLLOW_UP | CANCELED | User canceled mid-run |

On failure: `status = FAILED`, `error = <message>`, `stage` stays at the failed stage. The user can retry by calling `POST /rerun { stage: <failed_stage> }`.

`conversation` is the shared context for all LLM agents. Every agent reads it at invocation. Every user message and agent response is appended here.

`pending_sources` is the handoff channel between DataSourceDiscoveryAgent and DataAgent — see DataSourceDiscoveryAgent → DataAgent Handoff below.

`featurizer_config` default for the oil profile:
```json
{
  "windows": [5, 20, 60],
  "lags": [1, 5, 20],
  "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
  "energy_specific": true
}
```

---

### DataArtifact

Produced by DataAgent. One per DATA_GATHERING round (round increments on each refetch).

```python
class DataArtifact(SQLModel, table=True):
    id:                      UUID
    session_id:              UUID       # FK → Session
    round:                   int        # 1, 2, 3 ... increments on refetch
    sources:                 JSON       # DataSource[] — what was fetched
    data_manifest:           JSON       # shape, date coverage, missing %, summary stats
    raw_data:                JSON|None  # actual time series — null if raw_data_ref is set
    raw_data_ref:            str|None   # file path or S3 URI — used when size > 5MB
    source_hash:             str        # hash(market_profile + timeframe + sources)
    cached_from_session_id:  UUID|None  # provenance if cache hit
    cached_from_artifact_id: UUID|None
    cache_hit:               bool = False
    created_at:              datetime
```

`DataSource` shape:
```json
{
  "connector_id": "yfinance",
  "ticker": "CL=F",
  "params": { "start": "2023-01-01", "end": "2023-06-30" }
}
```

`data_manifest` shape:
```json
{
  "tickers": ["CL=F", "BZ=F", "DXY"],
  "date_range": { "start": "2023-01-01", "end": "2023-06-30" },
  "rows": 126,
  "missing_pct": { "CL=F": 0.0, "BZ=F": 0.8 },
  "summary_stats": { "CL=F": { "mean": 78.4, "std": 6.2, "min": 66.7, "max": 93.1 } }
}
```

---

### FeatureArtifact

Produced by FeaturizerService. One per FEATURIZING run.

```python
class FeatureArtifact(SQLModel, table=True):
    id:                          UUID
    session_id:                  UUID       # FK → Session
    data_artifact_id:            UUID       # FK → DataArtifact
    featurizer_config_snapshot:  JSON       # config at time of run (immutable snapshot)
    feature_manifest:            JSON       # column names, shapes — not the full matrix
    config_hash:                 str        # hash(data_artifact_id + featurizer_config)
    cached_from_session_id:      UUID|None
    cached_from_artifact_id:     UUID|None
    cache_hit:                   bool = False
    created_at:                  datetime
```

`feature_manifest` shape:
```json
{
  "n_features": 187,
  "n_rows": 126,
  "feature_families": {
    "rolling_stats": 54,
    "momentum": 48,
    "lag": 63,
    "regime": 22
  },
  "columns": ["CL=F_mean_5d", "CL=F_std_20d", "CL=F_roc_1d", ...]
}
```

The full feature matrix is not stored in the DB — it is computed on demand and passed directly to TabPFN.

---

### AnalysisResult

Produced in two phases: TabPFN fields written by TabPFNService, `summary` written by ExplanationAgent.

```python
class AnalysisResult(SQLModel, table=True):
    id:                      UUID
    session_id:              UUID       # FK → Session
    feature_artifact_id:     UUID       # FK → FeatureArtifact

    # --- TabPFN outputs (written by ANALYZING stage) ---
    regime:              JSON|None   # { "regime": "geopolitical_spike", "confidence": 0.82 }
    direction:           JSON|None   # { "direction": "up", "confidence": 0.71 }
    feature_importance:  JSON|None   # SHAP values from tabpfn-extensions
    drift:               JSON|None   # { "drift_detected": true, "psi_score": 0.23,
                                     #   "drifted_features": ["CL=F_roc_20d"] }
    backtest:            JSON|None   # walk-forward metrics, Sharpe ratio

    # --- LLM output (written by EXPLAINING stage) ---
    summary:             str|None

    feature_hash:                str        # hash(feature_artifact_id)
    cached_from_session_id:      UUID|None
    cached_from_artifact_id:     UUID|None
    cache_hit:                   bool = False
    created_at:                  datetime
```

---

### Connector

Persisted connector definitions. Includes built-in connectors (seeded at startup) and user-registered/generated connectors.

```python
class ConnectorType(str, Enum):
    BUILTIN   = "builtin"    # yfinance, fred, eia, gpr
    SPEC      = "spec"       # user-registered via POST /api/connectors
    GENERATED = "generated"  # built by ConnectorBuilderAgent — must pass tests

class Connector(SQLModel, table=True):
    id:          str           # slug, e.g. "yfinance", "iea_oil_report"
    name:        str
    description: str
    type:        ConnectorType
    spec:        JSON|None     # for SPEC type: endpoint, auth, field mappings
    code:        str|None      # for GENERATED type: Python source
    tests:       str|None      # for GENERATED type: pytest source — must pass before save
    is_active:   bool = True   # set to False if tests fail on reuse
    created_at:  datetime
```

---

### MarketProfile

Seeded at startup. Drives which connectors are recommended, what the default featurizer config is, and which regime labels TabPFN uses.

```python
class MarketProfile(SQLModel, table=True):
    id:                       str    # "oil", "sp500", "eurusd"
    name:                     str    # "Oil Markets"
    description:              str
    default_connectors:       JSON   # ["yfinance", "fred", "eia", "gpr"]
    default_featurizer_config: JSON
    regime_labels:            JSON   # ["bull_supercycle", "range_bound", "bust",
                                     #  "geopolitical_spike"]
    created_at:               datetime
```

---

## Agent & Service Definitions

### DataSourceDiscoveryAgent — LLM + HTTP tools

**Stage:** runs at session start, before DATA_GATHERING

**Reads from session:** `market_profile`, `timeframe_start/end`, `conversation`

**Tools:**
```
list_available_connectors()                         → built-in + registry
http_get(url, headers, params)                      → explore novel APIs
http_post(url, headers, body)
parse_response(content, format)                     → JSON | CSV | XML
save_connector_spec(id, name, spec)                 → write to Connector table
```

**Writes to session:** recommends data sources, appends recommendation to `conversation`

**Escalates to:** ConnectorBuilderAgent if HTTP primitives cannot handle the source

---

### DataAgent — LLM + tools

**Stage:** DATA_GATHERING

**Reads from session:** `market_profile`, `timeframe_start/end`, `conversation`, `featurizer_config` (to know which signals are expected), approved sources from DataSourceDiscoveryAgent

**Tools:**
```
fetch_yfinance(tickers, start, end)
fetch_fred(series_ids, start, end)
fetch_eia(dataset, start, end)
fetch_gpr(start, end)
fetch_custom_connector(connector_id, params)        → dispatches to registry
list_available_connectors()
```

**Writes to session:** new `DataArtifact` (round incremented if refetch). Updates `source_hash` for cache lookup.

---

### ReviewInterpreter — thin LLM call

**Stage:** USER_REVIEW gate (triggered by `POST /chat`)

**Not a full agent.** A single structured LLM call that classifies user intent and extracts updates.

**Input:** user message + current session state

**Output:**
```json
{
  "action": "advance" | "refetch" | "update_config",
  "updates": {
    "sources_to_add": ["baker_hughes_rig_count"],
    "featurizer_config_patch": { "windows": [5, 30, 90] }
  },
  "reply": "Adding Baker Hughes rig count and fetching updated data..."
}
```

- `advance` → stage transitions to FEATURIZING
- `refetch` → stage transitions back to DATA_GATHERING with updated source list
- `update_config` → `featurizer_config` patched on session → stage transitions to FEATURIZING

---

### FeaturizerService — deterministic

**Stage:** FEATURIZING

**Reads from session:** latest `DataArtifact.raw_data`, `Session.featurizer_config`

**Cache check:** `config_hash = hash(data_artifact_id + featurizer_config)` — searches all sessions for match. On hit: copies with provenance, skips computation.

**On miss:** runs `TimeSeriesFeaturizer` → writes `FeatureArtifact` with `feature_manifest` and `config_hash`.

No LLM involved.

---

### TabPFNService — deterministic

**Stage:** ANALYZING

**Reads from session:** latest `FeatureArtifact`, `market_profile` (determines regime labels)

**Cache check:** `feature_hash = hash(feature_artifact_id)` — searches all sessions. On hit: copies with provenance.

**On miss:** runs:
- `OilRegimeClassifier` → regime + confidence
- `DirectionClassifier` → direction + confidence
- SHAP via tabpfn-extensions → feature_importance
- Drift detection → drift
- Walk-forward backtest → backtest

Writes `AnalysisResult` (summary is null at this point).

No LLM involved.

---

### ExplanationAgent — LLM only, no tools

**Stage:** EXPLAINING

**Always re-runs** — even on full cache hit. Cheap (one LLM call) and the user's framing may differ from the original session.

**Reads from session:** `AnalysisResult` (regime, direction, SHAP, drift, backtest), `data_manifest`, `featurizer_config`, full `conversation`

**Writes to session:** `AnalysisResult.summary`. Streams the explanation to the frontend via WebSocket.

---

### FollowUpAgent — LLM + tools

**Stage:** FOLLOW_UP (triggered by `POST /chat`)

**Reads from session:** everything — full conversation, all artifacts, all analysis results

**Tools:**
```
explain_feature(feature_name)                       → detailed SHAP explanation
rerun_featurizer(featurizer_config_patch)           → patches config + triggers FEATURIZING
rerun_data_gathering(sources_to_add)                → triggers DATA_GATHERING
compare_sessions(session_id)                        → pulls prior session artifacts
```

**Writes to session:** appends to `conversation`. Can trigger stage regression by updating `session.stage` and enqueuing a background task.

---

### ConnectorBuilderAgent — LLM + sandboxed execution

**Stage:** invoked by `POST /api/connectors/build`, or escalated from DataSourceDiscoveryAgent

**The quality gate:** connector code is only saved to the registry if its generated tests pass.

**Tools:**
```
web_search(query)                                   → find API docs
write_connector_code(description, api_docs)         → generate Python connector
write_connector_tests(connector_code)               → generate pytest tests
execute_in_sandbox(connector_code, test_code)       → returns pass/fail + output
save_connector(code, tests, spec)                   → only callable after tests pass
```

**Workflow:**
```
web_search → find API docs
write_connector_code → draft implementation
write_connector_tests → draft tests
execute_in_sandbox → run tests
  ├── pass → save_connector → connector available in registry
  └── fail → iterate (fix code, re-run) → up to N iterations
               └── max iterations → tell user why, suggest upload fallback
```

**Saved connectors** carry their tests permanently. On each future session use, tests re-run first. If they fail, the connector is marked `is_active = False` and the user is notified (API changed, auth expired, etc.).

---

## Database Model Relationships

### Entity Relationship Diagram

```
┌─────────────────────┐
│    MarketProfile    │
│─────────────────────│
│ id: TEXT (PK)       │
│ name                │
│ description         │
│ default_connectors  │
│ default_feat_config │
│ regime_labels       │
│ created_at          │
└──────────┬──────────┘
           │ referenced by string (not FK — profiles are config, not rows)
           │
┌──────────▼──────────────────────────────────────┐
│                     Session                      │
│──────────────────────────────────────────────────│
│ id: UUID (PK)                                    │
│ market_profile: TEXT                             │
│ timeframe_start: DATE                            │
│ timeframe_end: DATE                              │
│ stage: TEXT                                      │
│ status: TEXT                                     │
│ error: TEXT (nullable)                           │
│ auto: BOOLEAN                                    │
│ featurizer_config: JSONB                         │
│ pending_sources: JSONB                           │
│ conversation: JSONB                              │
│ stage_history: JSONB                             │
│ created_at: TIMESTAMPTZ                          │
│ updated_at: TIMESTAMPTZ                          │
└──────────────────────┬───────────────────────────┘
                       │ 1
          ┌────────────┼─────────────┐
          │ *          │ *           │ *
          ▼            │             │
┌─────────────────┐    │             │
│  DataArtifact   │    │             │
│─────────────────│    │             │
│ id: UUID (PK)   │    │             │
│ session_id: UUID│    │             │
│   (FK→Session)  │    │             │
│ round: INTEGER  │    │             │
│ sources: JSONB  │    │             │
│ data_manifest:  │    │             │
│   JSONB         │    │             │
│ raw_data: JSONB │    │             │
│ source_hash:    │    │             │
│   TEXT (IDX)    │    │             │
│ cached_from_    │    │             │
│   session_id:   │    │             │
│   UUID (nullable│    │             │
│   FK→Session)   │    │             │
│ cached_from_    │    │             │
│   artifact_id:  │    │             │
│   UUID (nullable│    │             │
│   self-ref)     │    │             │
│ cache_hit: BOOL │    │             │
│ created_at      │    │             │
└────────┬────────┘    │             │
         │ 1           │             │
         │ *           ▼             │
         │  ┌──────────────────────┐ │
         │  │   FeatureArtifact    │ │
         │  │──────────────────────│ │
         └─►│ id: UUID (PK)        │ │
            │ session_id: UUID     │ │
            │   (FK→Session)       │ │
            │ data_artifact_id:    │ │
            │   UUID (FK→Data...)  │ │
            │ feat_config_snapshot │ │
            │   JSONB              │ │
            │ feature_manifest:    │ │
            │   JSONB              │ │
            │ config_hash:         │ │
            │   TEXT (IDX)         │ │
            │ cached_from_         │ │
            │   session_id: UUID   │ │
            │ cached_from_         │ │
            │   artifact_id: UUID  │ │
            │ cache_hit: BOOL      │ │
            │ created_at           │ │
            └─────────┬────────────┘ │
                      │ 1            │
                      │ *            ▼
                      │  ┌───────────────────────┐
                      │  │    AnalysisResult      │
                      │  │───────────────────────│
                      └─►│ id: UUID (PK)          │
                         │ session_id: UUID        │
                         │   (FK→Session)          │
                         │ feature_artifact_id:    │
                         │   UUID (FK→Feature...)  │
                         │ regime: JSONB           │
                         │ direction: JSONB        │
                         │ feature_importance:JSONB│
                         │ drift: JSONB            │
                         │ backtest: JSONB         │
                         │ summary: TEXT (nullable)│
                         │ feature_hash:           │
                         │   TEXT (IDX)            │
                         │ cached_from_            │
                         │   session_id: UUID      │
                         │ cached_from_            │
                         │   artifact_id: UUID     │
                         │ cache_hit: BOOL         │
                         │ created_at              │
                         └─────────────────────────┘

┌──────────────────────┐
│      Connector       │   (independent — no FK to Session)
│──────────────────────│
│ id: TEXT (PK)        │   referenced via DataArtifact.sources[].connector_id (JSONB)
│ name: TEXT           │
│ description: TEXT    │
│ type: TEXT           │   "builtin" | "spec" | "generated"
│ spec: JSONB (null)   │
│ code: TEXT (null)    │
│ tests: TEXT (null)   │
│ is_active: BOOLEAN   │
│ created_at           │
└──────────────────────┘
```

### Key Relationships

| Relationship | Cardinality | Foreign Key |
|---|---|---|
| Session → DataArtifact | 1 : many | `data_artifact.session_id` |
| Session → FeatureArtifact | 1 : many | `feature_artifact.session_id` |
| Session → AnalysisResult | 1 : many | `analysis_result.session_id` |
| DataArtifact → FeatureArtifact | 1 : many | `feature_artifact.data_artifact_id` |
| FeatureArtifact → AnalysisResult | 1 : many | `analysis_result.feature_artifact_id` |
| Session → Session (cache provenance) | 1 : many | `*.cached_from_session_id` (nullable) |
| Artifact → Artifact (cache provenance) | self-ref | `*.cached_from_artifact_id` (nullable) |

`MarketProfile` is not a foreign key — `Session.market_profile` stores the profile `id` as a plain string. Profiles are configuration, not transactional data. They are seeded at startup and rarely change.

`Connector` is not directly FK'd to `Session` — connectors are referenced inside `DataArtifact.sources` as a JSONB array, keeping the data fetch record self-contained.

### PostgreSQL Column Types

| Python / SQLModel type | PostgreSQL type | Notes |
|---|---|---|
| `UUID` | `UUID` | Native PostgreSQL UUID, generated via `gen_random_uuid()` |
| `str` | `TEXT` | No `VARCHAR(n)` — PostgreSQL TEXT is equally performant |
| `int` | `INTEGER` | `round`, counters |
| `bool` | `BOOLEAN` | `auto`, `cache_hit`, `is_active` |
| `date` | `DATE` | `timeframe_start`, `timeframe_end` |
| `datetime` | `TIMESTAMPTZ` | Always timezone-aware; stored as UTC |
| `dict` / `list` | `JSONB` | **Not JSON** — JSONB is binary, indexed, queryable |
| `str` (hash) | `TEXT` | `source_hash`, `config_hash`, `feature_hash` |
| `Enum` | `TEXT` | SQLModel stores enums as TEXT with Python-level validation |

All `JSONB` fields benefit from GIN indexes if queried frequently. Hash fields (`source_hash`, `config_hash`, `feature_hash`) use B-tree indexes for equality lookups in the cache system.

### Indexes

```sql
-- Cache lookup indexes (most performance-critical)
CREATE INDEX idx_data_artifact_source_hash     ON data_artifact(source_hash);
CREATE INDEX idx_feature_artifact_config_hash  ON feature_artifact(config_hash);
CREATE INDEX idx_analysis_result_feature_hash  ON analysis_result(feature_hash);

-- Session history listing
CREATE INDEX idx_session_created_at            ON session(created_at DESC);

-- Artifact lookup by session (used on every session GET)
CREATE INDEX idx_data_artifact_session_id      ON data_artifact(session_id);
CREATE INDEX idx_feature_artifact_session_id   ON feature_artifact(session_id);
CREATE INDEX idx_analysis_result_session_id    ON analysis_result(session_id);

-- Connector active lookup
CREATE INDEX idx_connector_is_active           ON connector(is_active);
```

---

## Chat Window Stage Gating

### Stage Behaviour

The chat window behaves differently depending on the current session stage. During active stages (agent or service running), input is disabled and the window shows the live stream. During interactive stages, the user can type.

| Stage | Chat input | `/proceed` | What the chat window shows |
|---|---|---|---|
| CONFIGURING | disabled | — | "Starting data discovery..." |
| DATA_GATHERING | disabled | — | Live agent stream: thoughts, tool calls, results |
| USER_REVIEW | **enabled** | **enabled** | Data dashboard + chat input |
| FEATURIZING | disabled | — | "Running featurizer..." with progress |
| ANALYZING | disabled | — | "Running TabPFN..." with progress |
| EXPLAINING | disabled | — | Live explanation streaming |
| FOLLOW_UP | **enabled** | — | Full dashboard + chat input |

### Stage Validation on Endpoints

`POST /chat` and `POST /proceed` enforce stage constraints on the backend. Calling them at the wrong stage returns `409 Conflict` — the frontend disables input during active stages, but the backend enforces it as a hard rule regardless.

```python
CHAT_ALLOWED_STAGES    = {SessionStage.USER_REVIEW, SessionStage.FOLLOW_UP}
PROCEED_ALLOWED_STAGES = {SessionStage.USER_REVIEW}

# POST /sessions/{id}/chat
if session.stage not in CHAT_ALLOWED_STAGES:
    raise HTTPException(409, f"chat not available at stage {session.stage}")

# POST /sessions/{id}/proceed
if session.stage not in PROCEED_ALLOWED_STAGES:
    raise HTTPException(409, f"proceed not available at stage {session.stage}")
```

All other stage-triggering endpoints (`/rerun`, `/cancel`) are valid only when an appropriate background task is active; they also return `409` otherwise.

### Stage History

`Session` carries an append-only `stage_history` field — a log of when each stage was entered. Used by the frontend to show how long each stage took, and by debugging/observability tooling.

```python
# Added to Session model
stage_history: JSONB  # append-only

# Shape — one entry appended each time session.stage changes
[
  { "stage": "configuring",    "entered_at": "2026-05-31T10:00:00Z" },
  { "stage": "data_gathering", "entered_at": "2026-05-31T10:00:01Z" },
  { "stage": "user_review",    "entered_at": "2026-05-31T10:00:18Z" },
  { "stage": "featurizing",    "entered_at": "2026-05-31T10:01:45Z" },
  ...
]
```

The stage transition helper that all agents and services call:

```python
def transition_stage(session: Session, new_stage: SessionStage) -> None:
    session.stage = new_stage
    session.stage_history = [
        *session.stage_history,
        {"stage": new_stage.value, "entered_at": datetime.now(UTC).isoformat()},
    ]
    session.updated_at = datetime.now(UTC)
```

---

## Artifact Cache

### Within-session cache

Before each deterministic stage runs, the service checks whether a matching artifact already exists in the current session:

```
FEATURIZING:  config_hash = hash(data_artifact_id + featurizer_config)
              → search FeatureArtifact WHERE session_id = current AND config_hash = X
ANALYZING:    feature_hash = hash(feature_artifact_id)
              → search AnalysisResult WHERE session_id = current AND feature_hash = X
```

### Cross-session cache

When a new session starts, each stage checks globally:

```
FEATURIZING:  → search FeatureArtifact WHERE config_hash = X (any session)
ANALYZING:    → search AnalysisResult WHERE feature_hash = X (any session)
```

On a hit, the artifact is **copied** into the new session with provenance:

```json
{
  "cache_hit": true,
  "cached_from_session_id": "abc-123",
  "cached_from_artifact_id": "def-456"
}
```

The WebSocket stream includes a `cache_hit` event:
```json
{ "type": "cache_hit", "stage": "ANALYZING", "source_session_id": "abc-123", "date": "2026-05-15" }
```

`ExplanationAgent` always re-runs regardless of cache state.

---

## DataSourceDiscoveryAgent → DataAgent Handoff

DataSourceDiscoveryAgent and DataAgent run **sequentially and automatically** — there is no user gate between them. Adding a second gate here would create three user interruption points (source approval, data review, analysis), which is too many for the common case.

**Flow:**

```
POST /api/sessions
  → DataSourceDiscoveryAgent starts in background
  → streams recommendations to frontend
  → writes approved sources to Session.pending_sources
  → session.stage stays CONFIGURING during this phase
  → on completion: session.stage → DATA_GATHERING, DataAgent starts automatically
       │
       ▼
DataAgent reads Session.pending_sources
  → fetches each source
  → clears pending_sources on completion
  → writes DataArtifact
  → session.stage → USER_REVIEW
```

`pending_sources` is the handoff channel — a JSONB array of `DataSource` objects written by DataSourceDiscoveryAgent and consumed by DataAgent. It is cleared after DATA_GATHERING completes.

The user can still influence this flow by calling `POST /cancel` during DATA_GATHERING if they want to stop and adjust.

**Auto mode:** DataSourceDiscoveryAgent still runs and streams recommendations (its output is useful context), but the USER_REVIEW gate is skipped — FEATURIZING starts immediately after DATA_GATHERING completes.

---

## Request & Response Shapes

### `POST /api/sessions`
```json
// Request
{
  "market_profile": "oil",
  "timeframe_start": "2023-01-01",
  "timeframe_end": "2023-06-30",
  "auto": false
}

// Response — 202 Accepted
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `GET /api/sessions/{id}`
```json
// Response — 200 OK
// Returns session state with artifact IDs only — not full artifact data.
// Full artifact data is fetched separately via GET /api/sessions/{id}/artifacts/{artifact_id}
{
  "session_id": "550e8400-...",
  "market_profile": "oil",
  "timeframe_start": "2023-01-01",
  "timeframe_end": "2023-06-30",
  "stage": "follow_up",
  "status": "waiting",
  "error": null,
  "auto": false,
  "featurizer_config": { "windows": [5, 20, 60], "lags": [1, 5, 20], "feature_families": [...] },
  "conversation": [...],
  "stage_history": [
    { "stage": "configuring",    "entered_at": "2026-05-31T10:00:00Z" },
    { "stage": "data_gathering", "entered_at": "2026-05-31T10:00:01Z" },
    ...
  ],
  "artifacts": {
    "data": [
      { "artifact_id": "uuid-1", "round": 1, "cache_hit": false, "created_at": "..." }
    ],
    "features": [
      { "artifact_id": "uuid-2", "cache_hit": false, "created_at": "..." }
    ],
    "analysis": [
      { "artifact_id": "uuid-3", "cache_hit": false, "has_summary": true, "created_at": "..." }
    ]
  },
  "created_at": "2026-05-31T10:00:00Z",
  "updated_at": "2026-05-31T10:05:30Z"
}
```

### `POST /api/sessions/{id}/chat`
```json
// Request
{ "message": "Why is drift elevated?" }

// Response — 202 Accepted
// The agent's reply arrives over WebSocket, not in this response
{ "session_id": "550e8400-..." }
```

### `POST /api/sessions/{id}/rerun`
```json
// Request
{
  "stage": "featurizing",
  "featurizer_config_patch": { "windows": [5, 30, 90] }   // optional — applied before rerun
}

// Response — 202 Accepted
{ "session_id": "550e8400-..." }
```

### `POST /api/sessions/{id}/proceed`
```json
// No request body required

// Response — 202 Accepted
{ "session_id": "550e8400-..." }
```

### `POST /api/sessions/{id}/cancel`
```json
// No request body required

// Response — 200 OK
{ "session_id": "550e8400-...", "stage": "data_gathering", "status": "canceled" }
```

### `POST /api/sessions/{id}/upload`
```json
// Request — multipart/form-data
// Field: file (CSV or Parquet)
// Field: source_name (string, e.g. "My Custom OPEC Data")

// Response — 202 Accepted
{ "artifact_id": "uuid-new-data-artifact" }
```

Supported upload formats: **CSV** and **Parquet**. Max file size: **50MB**. The backend parses the file, builds the `data_manifest`, and writes a `DataArtifact` with `source_type: "upload"`. This bypasses DataAgent entirely.

### `GET /api/sessions/{id}/artifacts/{artifact_id}`
```json
// Response — 200 OK — full artifact data for dashboard rendering
// Shape varies by artifact kind:

// DataArtifact
{
  "kind": "data",
  "artifact_id": "...",
  "round": 1,
  "sources": [...],
  "data_manifest": { "tickers": [...], "rows": 126, "missing_pct": {...}, "summary_stats": {...} },
  "cache_hit": false,
  "cached_from_session_id": null
}

// AnalysisResult
{
  "kind": "analysis",
  "artifact_id": "...",
  "regime": { "regime": "geopolitical_spike", "confidence": 0.82 },
  "direction": { "direction": "up", "confidence": 0.71 },
  "feature_importance": { "top_features": [...] },
  "drift": { "drift_detected": true, "psi_score": 0.23 },
  "backtest": { "sharpe": 1.4, "accuracy": 0.71 },
  "summary": "Markets are in a geopolitical spike regime...",
  "cache_hit": false
}
```

Note: `raw_data` is **never returned** to the frontend — it is server-side only, consumed exclusively by FeaturizerService.

---

## Operational Concerns

### raw_data Storage

`DataArtifact.raw_data` is stored as JSONB for datasets under **5MB** (typically ≤ 3 years × 10 tickers × daily frequency). Above that threshold, data is written to a file and `raw_data_ref` holds the path/URI instead (`raw_data` is null).

- **Early PRs (1–4):** local filesystem only. `raw_data_ref` is a relative file path under `data/artifacts/{artifact_id}.parquet`.
- **PR 5+:** S3-compatible storage (configurable via `ARTIFACT_STORAGE_BACKEND` env var: `local` | `s3`).

FeaturizerService reads from `raw_data` if set, otherwise reads from the file at `raw_data_ref`. This is transparent to callers.

---

### WebSocket Reconnection

The WebSocket stream is **live-only** — it does not replay past messages on reconnect. This keeps the infrastructure simple (plain Redis pub/sub, no message log).

Recovery surface on reconnect or page refresh:
1. Frontend calls `GET /api/sessions/{id}` — returns current `stage`, `status`, `artifacts`, `conversation`, and `stage_history`
2. Frontend reconnects to `WS /ws/sessions/{id}/stream` for future messages
3. If `status = RUNNING`, the stream resumes mid-stream (the background task is still publishing)

For the dashboard: all completed artifact data is available via `GET /api/sessions/{id}/artifacts/{id}` at any time. Nothing is lost — only the live streaming log (thoughts, tool calls) of a completed stage cannot be replayed.

---

### Concurrency Protection

Every endpoint that starts a background task checks `session.status` first. If `status == RUNNING`, the endpoint returns `409 Conflict` — a task is already active for this session.

```python
# Applied to: POST /proceed, POST /rerun, POST /chat (at FOLLOW_UP)
if session.status == SessionStatus.RUNNING:
    raise HTTPException(409, "a task is already running for this session — POST /cancel to stop it")
```

`POST /cancel` is the only endpoint valid while `status == RUNNING`. After cancellation (`status = CANCELED`), the user can call `POST /rerun` to restart from the failed/canceled stage.

---

## API

```
Sessions
  POST   /api/sessions                               create session → DataSourceDiscoveryAgent starts
  GET    /api/sessions                               list sessions (history)
  GET    /api/sessions/{id}                          full session state + current stage
  DELETE /api/sessions/{id}                          delete session
  POST   /api/sessions/{id}/proceed                  USER_REVIEW gate: "satisfied" → FEATURIZING
  POST   /api/sessions/{id}/rerun                    { "stage": "FEATURIZING" | "ANALYZING" | "DATA_GATHERING" }
  POST   /api/sessions/{id}/cancel                   cancel current running agent/service
  POST   /api/sessions/{id}/chat                     natural language at USER_REVIEW or FOLLOW_UP
  POST   /api/sessions/{id}/upload                   upload data file → DataArtifact directly

Artifacts
  GET    /api/sessions/{id}/artifacts/{artifact_id}  fetch artifact data for dashboard rendering

Market Profiles
  GET    /api/profiles                               list available profiles
  GET    /api/profiles/{id}                          profile details (connectors, feature config, regime labels)

Connectors
  GET    /api/connectors                             list built-in + user-registered
  GET    /api/connectors/{id}                        connector details
  POST   /api/connectors                             register connector spec manually
  DELETE /api/connectors/{id}                        remove user-registered connector
  POST   /api/connectors/build                       trigger ConnectorBuilderAgent

WebSocket
  WS     /ws/sessions/{id}/stream                   stream all activity + stage transitions
```

All agent-triggering endpoints return `202 Accepted` immediately. Work runs in a FastAPI `BackgroundTask`.

---

## WebSocket Protocol

All messages are JSON lines on `WS /ws/sessions/{id}/stream`.

```json
{ "type": "stage_transition",  "from": "DATA_GATHERING",  "to": "USER_REVIEW" }
{ "type": "thought",           "agent": "DataAgent",       "content": "Fetching EIA inventory data..." }
{ "type": "tool_call",         "agent": "DataAgent",       "tool": "fetch_eia",     "input": {...} }
{ "type": "tool_result",       "agent": "DataAgent",       "tool": "fetch_eia",     "output": {...} }
{ "type": "artifact_ready",    "kind": "data",             "artifact_id": "...",    "manifest": {...} }
{ "type": "artifact_ready",    "kind": "analysis",         "artifact_id": "...",    "regime": {...} }
{ "type": "cache_hit",         "stage": "ANALYZING",       "source_session_id": "...","date": "2026-05-15" }
{ "type": "done",              "stage": "EXPLAINING",      "summary": "..." }
{ "type": "error",             "message": "..." }
```

---

## Market Profiles

A market profile drives: which data connectors are recommended, the default featurizer config, and the regime labels passed to TabPFN.

### Oil (fully built out)

```json
{
  "id": "oil",
  "name": "Oil Markets",
  "default_connectors": ["yfinance", "fred", "eia", "gpr"],
  "default_featurizer_config": {
    "windows": [5, 20, 60],
    "lags": [1, 5, 20],
    "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
    "energy_specific": true
  },
  "regime_labels": ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]
}
```

### Other profiles (stub — later PRs)

`sp500`, `eurusd`, `custom` — same structure, connectors and regime labels TBD.

---

## PR Breakdown

### PR 1 — Cleanup + Session Data Model
- Remove old `Run` model, old `run_agent_loop`, old `/api/analyze` and `/api/runs` routes
- Remove old chat window code (PR1/PR2 plans) from `docs/`
- New `Session`, `DataArtifact`, `FeatureArtifact`, `AnalysisResult`, `Connector`, `MarketProfile` SQLModel models
- Alembic migrations
- Basic session CRUD endpoints: `POST`, `GET`, `DELETE /api/sessions`, `GET /api/sessions/{id}`
- `GET /api/profiles`, `GET /api/profiles/{id}` (seeded oil profile)
- WebSocket stub (connects, echoes events, no agents yet)

### PR 2 — Deterministic Pipeline Stages
- `FeaturizerService` wrapping existing `TimeSeriesFeaturizer`
- `TabPFNService` wrapping existing `OilRegimeClassifier` + `DirectionClassifier`
- Stage machine: `POST /proceed`, `POST /rerun`, `POST /cancel`
- Within-session artifact cache (config_hash + feature_hash lookups)
- Background task pattern wired for both services
- Full pipeline: FEATURIZING → ANALYZING runs end-to-end

### PR 3 — DataSourceDiscoveryAgent + DataAgent
- Built-in connector registry seeded (yfinance, FRED, EIA, GPR)
- `DataSourceDiscoveryAgent` with HTTP primitive tools
- `DataAgent` with full tool set + connector dispatch
- `ReviewInterpreter` (thin LLM call at USER_REVIEW)
- `POST /sessions/{id}/upload` → DataArtifact
- `GET /api/connectors`, `POST /api/connectors`
- Full pipeline from session creation to USER_REVIEW gate

### PR 4 — ExplanationAgent + FollowUpAgent
- `ExplanationAgent` with WebSocket streaming
- `FollowUpAgent` with stage regression tools
- `POST /sessions/{id}/chat` wired to both agents based on current stage
- `GET /api/sessions/{id}/artifacts/{artifact_id}` for dashboard rendering
- Full end-to-end pipeline working

### PR 5 — Cross-Session Artifact Cache
- Global artifact cache lookup across sessions
- Provenance copying (`cached_from_session_id`, `cached_from_artifact_id`)
- `cache_hit` WebSocket event
- Cache indicators surfaced in session state

### PR 6 — Market Profiles
- Market profile system fully wired (profile drives connectors, featurizer config, regime labels)
- Oil profile fully built out with all connectors
- Stub profiles for `sp500`, `eurusd`
- Profile selection drives DataSourceDiscoveryAgent recommendations

### PR 7 — ConnectorBuilderAgent *(standalone, last)*
- Sandbox infrastructure (restricted subprocess or Docker)
- `ConnectorBuilderAgent`: web_search + write_code + write_tests + execute_in_sandbox
- Tests must pass before `save_connector`
- Stale connector detection: tests re-run on first use per session; `is_active = False` on failure
- `POST /api/connectors/build` endpoint
- `DELETE /api/connectors/{id}`
