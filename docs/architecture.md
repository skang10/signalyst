# Signalyst — Architecture Diagrams

Four Mermaid diagrams derived from `docs/backend-redesign.md` and `docs/frontend-redesign.md`.

---

## 1. System Components

High-level infrastructure: how the frontend, backend, storage, LLM API, and external data sources connect, and how the 202 → BackgroundTask → Redis → WebSocket pattern works.

```mermaid
graph LR
    subgraph FE["Frontend — Next.js :3000"]
        UI["Pages & Components"]
        Store["useSessionStore"]
        WSClient["useSessionStream"]
    end

    subgraph BE["FastAPI Backend — :8000"]
        REST["REST Endpoints"]
        BG["BackgroundTask\nAgent / Service execution"]
        WSH["WebSocket Handler"]
        RedisSub["Redis Subscriber"]
    end

    subgraph Storage["Storage"]
        PG[("PostgreSQL\nSQLModel · asyncpg")]
        RedisPS[("Redis\npub/sub")]
        Files["File Storage\nparquet artifacts\nlocal · S3"]
    end

    subgraph External["External"]
        ClaudeAPI["Claude API\nLLM agents"]
        DataSrc["Data Sources\nyfinance · FRED · EIA · GPR"]
    end

    UI -->|REST| REST
    WSClient -->|"WS /ws/sessions/id/stream"| WSH
    REST -->|"202 Accepted"| BG
    BG -->|"publish events"| RedisPS
    RedisPS -->|subscribe| RedisSub
    RedisSub -->|"forward JSON"| WSH
    WSH -->|stream| WSClient
    BG -->|"reads / writes"| PG
    BG -->|"write parquet"| Files
    BG -->|LLM calls| ClaudeAPI
    BG -->|"fetch time-series"| DataSrc
    REST -->|"reads / writes"| PG
```

---

## 2. Session Pipeline & Stage Machine

All 7 stages, transition triggers, USER_REVIEW gate branches, auto mode bypass, FOLLOW_UP rerun regression, and terminal FAILED / CANCELED states. `POST /rerun { stage }` can resume from any prior stage — existing artifacts in the DB are reused, only the specified stage and beyond re-run.

```mermaid
flowchart TD
    START(["POST /api/sessions"]) --> CONFIGURING

    CONFIGURING["CONFIGURING\nDataSourceDiscoveryAgent\nstreams recommendations\nwrites pending_sources"]
    DATA_GATHERING["DATA_GATHERING\nDataAgent fetches sources\nwrites DataArtifact"]
    USER_REVIEW["USER_REVIEW\nchat enabled · user gate"]
    FEATURIZING["FEATURIZING\nFeaturizerService\nwrites FeatureArtifact"]
    ANALYZING["ANALYZING\nTabPFNService\nwrites AnalysisResult"]
    EXPLAINING["EXPLAINING\nExplanationAgent\nstreams + writes summary"]
    FOLLOW_UP["FOLLOW_UP\nchat enabled · user gate"]
    FAILED(["FAILED\nsee session.error"])
    CANCELED(["CANCELED"])

    CONFIGURING -->|"auto-transition\npending_sources ready"| DATA_GATHERING
    DATA_GATHERING -->|"DataArtifact written"| USER_REVIEW
    USER_REVIEW -->|"POST /proceed"| FEATURIZING
    USER_REVIEW -->|"POST /chat — add source"| DATA_GATHERING
    USER_REVIEW -->|"POST /chat — update config"| FEATURIZING
    FEATURIZING -->|"FeatureArtifact written"| ANALYZING
    ANALYZING -->|"AnalysisResult written"| EXPLAINING
    EXPLAINING -->|"summary written"| FOLLOW_UP
    FOLLOW_UP -->|"POST /rerun\nstage=FEATURIZING"| FEATURIZING
    FOLLOW_UP -->|"POST /rerun\nstage=DATA_GATHERING"| DATA_GATHERING

    DATA_GATHERING -.->|"auto=true:\nskip USER_REVIEW"| FEATURIZING

    DATA_GATHERING -->|task crash| FAILED
    FEATURIZING -->|task crash| FAILED
    ANALYZING -->|task crash| FAILED
    FAILED -->|"POST /rerun\nstage=data_gathering"| DATA_GATHERING
    FAILED -->|"POST /rerun\nstage=featurizing\n(DataArtifact reused)"| FEATURIZING
    FAILED -->|"POST /rerun\nstage=analyzing\n(FeatureArtifact reused)"| ANALYZING

    DATA_GATHERING -->|"POST /cancel"| CANCELED
    FEATURIZING -->|"POST /cancel"| CANCELED
    ANALYZING -->|"POST /cancel"| CANCELED
    CANCELED -->|"POST /rerun\nstage=data_gathering"| DATA_GATHERING
    CANCELED -->|"POST /rerun\nstage=featurizing\n(DataArtifact reused)"| FEATURIZING
    CANCELED -->|"POST /rerun\nstage=analyzing\n(FeatureArtifact reused)"| ANALYZING
```

---

## 3. Multi-Agent Pipeline

Which agent or deterministic service runs at each stage, their key tools, inputs/outputs, and handoff points. LLM agents and deterministic services are styled separately.

```mermaid
flowchart TD
    DSDA["DataSourceDiscoveryAgent\nLLM + HTTP tools\n---\nlist_available_connectors\nhttp_get · http_post · parse_response\nsave_connector_spec\n---\nWrites: pending_sources"]

    DA["DataAgent\nLLM + fetch tools\n---\nfetch_yfinance · fetch_fred\nfetch_eia · fetch_gpr\nfetch_custom_connector\n---\nWrites: DataArtifact"]

    RI["ReviewInterpreter\nthin LLM call\n---\nClassifies intent:\nadvance · refetch · update_config\nPatches: featurizer_config"]

    FS_SVC["FeaturizerService\ndeterministic\n---\nReads: raw_data + featurizer_config\nCache: config_hash lookup\nRuns: TimeSeriesFeaturizer\nWrites: FeatureArtifact + parquet"]

    TABPFN["TabPFNService\ndeterministic\n---\nReads: FeatureArtifact + market_profile\nCache: feature_hash lookup\nRuns: OilRegimeClassifier\nDirectionClassifier · SHAP · drift · backtest\nWrites: AnalysisResult"]

    EA["ExplanationAgent\nLLM only — no tools\n---\nReads: AnalysisResult + conversation\nStreams summary via WebSocket\nWrites: AnalysisResult.summary"]

    FUA["FollowUpAgent\nLLM + regression tools\n---\nexplain_feature\nrerun_featurizer\nrerun_data_gathering\ncompare_sessions\n---\nCan trigger stage regression"]

    CBA["ConnectorBuilderAgent\nLLM + sandboxed execution\n---\nweb_search · write_connector_code\nwrite_connector_tests\nexecute_in_sandbox · save_connector\n---\nQuality gate: tests must pass"]

    DSDA -->|"pending_sources\nhandoff channel"| DA
    DA -->|DataArtifact| RI
    RI -->|"advance / update_config"| FS_SVC
    RI -->|refetch| DA
    FS_SVC -->|FeatureArtifact| TABPFN
    TABPFN -->|AnalysisResult| EA
    EA -->|summary complete| FUA
    FUA -.->|rerun_featurizer| FS_SVC
    FUA -.->|rerun_data_gathering| DA
    DSDA -.->|escalates to| CBA
    CBA -.->|"saves connector\nto registry"| DA

    classDef llm fill:#1e3a5f,stroke:#3b82f6,color:#f9fafb
    classDef det fill:#14532d,stroke:#22c55e,color:#f9fafb
    classDef thin fill:#3b1f5e,stroke:#a855f7,color:#f9fafb

    class DSDA,DA,EA,FUA,CBA llm
    class FS_SVC,TABPFN det
    class RI thin
```

**Legend:** Blue = LLM agent · Green = deterministic service · Purple = thin LLM call

---

## 4a. Data & Artifact Flow

How raw data flows through the pipeline, how the three-level artifact cache works (source_hash → config_hash → feature_hash), and the two storage tiers for raw data.

```mermaid
flowchart LR
    subgraph Sources["External Sources"]
        YF["yfinance"]
        FRED_SRC["FRED"]
        EIA_SRC["EIA API"]
        GPR_SRC["GPR Index"]
        UPL["File Upload\nCSV · Parquet"]
    end

    subgraph DA_box["DataArtifact"]
        RAW_INLINE["raw_data\nJSONB\nsmall datasets"]
        RAW_REF["raw_data_ref\npath / S3 URI\nover 5 MB"]
        SH["source_hash\nhash of market_profile\n+ timeframe + sources"]
    end

    subgraph FA_box["FeatureArtifact"]
        FMAT["feature_matrix_ref\nparquet file"]
        MH["matrix_hash"]
        CH["config_hash\nhash of source_hash\n+ featurizer_config"]
    end

    subgraph AR_box["AnalysisResult"]
        RES["regime · direction\nSHAP · drift · backtest"]
        SUM["summary\nfrom ExplanationAgent"]
        FH["feature_hash\nhash of matrix_hash\n+ regime_labels\n+ analysis_config"]
    end

    subgraph Cache["Cross-Session Cache"]
        C1["FeatureArtifact cache\nconfig_hash lookup\nacross all sessions"]
        C2["AnalysisResult cache\nfeature_hash lookup\nacross all sessions"]
    end

    Sources --> RAW_INLINE
    Sources --> RAW_REF
    UPL --> RAW_INLINE
    RAW_INLINE -->|"TimeSeriesFeaturizer"| FMAT
    RAW_REF -->|"TimeSeriesFeaturizer"| FMAT
    FMAT -->|"TabPFNService"| RES
    RES -->|"ExplanationAgent"| SUM
    SH --> CH
    CH --> FH

    CH -.->|"lookup"| C1
    FH -.->|"lookup"| C2
    C1 -.->|"cache hit:\ncopy artifact\nskip computation"| FA_box
    C2 -.->|"cache hit:\ncopy artifact\nskip computation"| AR_box
```

---

## 4b. Database Schema

Entity relationships for all six tables. Hash fields with indexes are marked `IDX`.

```mermaid
erDiagram
    MarketProfile {
        text id PK
        text name
        text description
        jsonb default_connectors
        jsonb default_featurizer_config
        jsonb regime_labels
        timestamptz created_at
    }

    Session {
        uuid id PK
        text market_profile
        date timeframe_start
        date timeframe_end
        text stage
        text status
        text error
        boolean auto
        jsonb featurizer_config
        jsonb pending_sources
        jsonb conversation
        jsonb activity_events
        jsonb stage_history
        timestamptz created_at
        timestamptz updated_at
    }

    DataArtifact {
        uuid id PK
        uuid session_id FK
        integer round
        jsonb sources
        jsonb data_manifest
        jsonb raw_data
        text raw_data_ref
        text source_hash "IDX"
        uuid cached_from_session_id
        uuid cached_from_artifact_id
        boolean cache_hit
        timestamptz created_at
    }

    FeatureArtifact {
        uuid id PK
        uuid session_id FK
        uuid data_artifact_id FK
        jsonb featurizer_config_snapshot
        jsonb feature_manifest
        text feature_matrix_ref
        text matrix_hash
        text config_hash "IDX"
        uuid cached_from_session_id
        uuid cached_from_artifact_id
        boolean cache_hit
        timestamptz created_at
    }

    AnalysisResult {
        uuid id PK
        uuid session_id FK
        uuid feature_artifact_id FK
        jsonb regime
        jsonb direction
        jsonb feature_importance
        jsonb drift
        jsonb backtest
        text summary
        text feature_hash "IDX"
        uuid cached_from_session_id
        uuid cached_from_artifact_id
        boolean cache_hit
        timestamptz created_at
    }

    Connector {
        text id PK
        text name
        text description
        text type
        jsonb spec
        text code
        text tests
        boolean is_active
        timestamptz created_at
    }

    Session ||--o{ DataArtifact : "has"
    Session ||--o{ FeatureArtifact : "has"
    Session ||--o{ AnalysisResult : "has"
    DataArtifact ||--o{ FeatureArtifact : "produces"
    FeatureArtifact ||--o{ AnalysisResult : "produces"
```
