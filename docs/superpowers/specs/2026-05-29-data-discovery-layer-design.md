# Data Discovery Layer & User-Extensible Connectors — Design Spec

**Session:** 8
**Branch:** `feat/improve-agent-loop`
**Date:** 2026-05-29

---

## Goal

Replace the hardcoded `fetch_data` tool with a two-tool data layer — `list_data_sources` and `fetch_from_source` — backed by a connector registry that auto-discovers manifests. The agent moves from "fetch these specific tickers" to "discover what's available, reason about what the analysis needs, then fetch it." Users can extend the available connectors by dropping a Python file + manifest into `backend/src/data/connectors/`.

---

## Problem with the Current Approach

`fetch_data` in `loop.py` is called with a fixed list of tickers and FRED series hardcoded into the system prompt. The agent never decides what data to pull — the prompt decides for it. This means:

- New data sources require system prompt edits, not connector additions
- Missing API keys cause silent skips with no agent awareness
- Expensive fetches (large historical windows) run without user consent
- Users cannot add their own data sources at all

---

## Architecture

```
Agent loop
    │
    ├── list_data_sources()          ← new tool
    │       └── ConnectorRegistry.list()
    │               └── scans connectors/ for manifest.yaml files
    │                   checks env for required keys
    │                   returns available[] + blocked[]
    │
    └── fetch_from_source(name, params)   ← new tool (replaces fetch_data)
            └── ConnectorRegistry.fetch(name, params, context)
                    ├── Tier 1/2/3: fetches and stores in context.signals
                    └── Tier 4 (compute_tier: high):
                            publishes confirmation_required to Redis
                            awaits confirm/{run_id} Redis signal
                            then fetches

backend/src/data/
├── connectors/
│   ├── yfinance/
│   │   ├── connector.py
│   │   └── manifest.yaml
│   ├── fred/
│   │   ├── connector.py
│   │   └── manifest.yaml
│   ├── gpr/
│   │   ├── connector.py
│   │   └── manifest.yaml
│   └── eia/
│       ├── connector.py
│       └── manifest.yaml
└── registry.py                 ← ConnectorRegistry (replaces connectors.py)
```

---

## Connector Manifest Schema

Each connector directory contains a `manifest.yaml`:

```yaml
name: fred                          # unique identifier, matches directory name
description: >
  FRED macro series from the St. Louis Fed — industrial production,
  unemployment, yield curve, and more.
provides:                           # semantic tags for agent reasoning
  - macro_series
  - economic_indicators
params:                             # JSON Schema object for fetch() params
  type: object
  properties:
    series_ids:
      type: array
      items: {type: string}
      description: "FRED series IDs, e.g. ['INDPRO', 'UNRATE']"
  required: [series_ids]
requires:
  env: FRED_API_KEY                 # omit if no key needed
compute_tier: low                   # low | high
examples:
  - series_ids: ["INDPRO", "UNRATE"]
```

`compute_tier: high` means the connector triggers a user confirmation gate before executing (e.g., a connector that fetches 20 years of tick data or runs a heavy computation).

---

## ConnectorRegistry

`backend/src/data/registry.py` — replaces the current `connectors.py` flat module.

```python
@dataclass
class ConnectorMeta:
    name: str
    description: str
    provides: list[str]
    params_schema: dict          # JSON Schema for fetch() params
    requires_env: str | None     # env var name, or None
    compute_tier: str            # "low" | "high"
    examples: list[dict]
    module: ModuleType           # imported connector.py

class ConnectorRegistry:
    def scan(self, connectors_dir: Path) -> None: ...
    def list(self) -> dict:
        # returns {"available": [...meta dicts...], "blocked": [...{name, reason}...]}
    def fetch(self, name: str, params: dict, context: AgentContext) -> dict: ...
    def is_available(self, name: str) -> bool: ...
```

`scan()` is called once at import time, iterating all subdirectories of `connectors/` that contain a `manifest.yaml`. For each, it:
1. Parses the manifest
2. Imports `connector.py` via `importlib`
3. Checks whether `requires_env` is set in the environment
4. Stores the `ConnectorMeta`

`list()` splits the registry into `available` (env key present or not required) and `blocked` (env key missing), returning both lists with enough metadata for the agent to reason about what it can and can't use.

`fetch()` imports the connector's `fetch(params, context)` function and calls it. If `compute_tier == "high"`, it first emits a `confirmation_required` event and awaits the confirmation signal before proceeding (see Confirmation Gate below).

---

## Connector Interface

Each `connector.py` must expose one function:

```python
def fetch(params: dict, context: AgentContext) -> dict:
    """
    Fetch data and store results in context.signals.
    Returns a summary dict: {"fetched": {name: row_count}, "skipped": [...]}
    """
```

The connector is responsible for reading its own API key from `settings` or `os.environ`. The registry does not inject keys — connectors declare what they need and retrieve it themselves.

---

## New Agent Tools

### `list_data_sources()`

No parameters. Returns:

```json
{
  "available": [
    {
      "name": "yfinance",
      "description": "...",
      "provides": ["price_series"],
      "params_schema": {...},
      "examples": [...]
    }
  ],
  "blocked": [
    {
      "name": "fred",
      "reason": "FRED_API_KEY not set"
    }
  ]
}
```

The agent uses this to understand what data it can actually pull before committing to a fetch plan.

### `fetch_from_source(source_name, params)`

Parameters:
- `source_name` (string): matches a connector's `name` field
- `params` (object): connector-specific, validated against the connector's `params_schema`

Returns the connector's fetch summary on success, or `{"error": "blocked", "reason": "..."}` / `{"error": "invalid_params", "detail": "..."}` on failure — never raises, so the agent always receives a result it can reason about.

---

## Confirmation Gate (Tier 4)

When `fetch_from_source` is called on a connector with `compute_tier: high`:

1. Registry publishes to Redis: `{"type": "confirmation_required", "source": name, "params": params, "message": "..."}`
2. Registry blocks on `await redis.blpop(f"confirm:{run_id}", timeout=120)`
3. Frontend receives the WebSocket event and shows a prompt (frontend implementation deferred)
4. User clicks confirm → backend receives the Redis signal → fetch proceeds
5. If timeout (120s) expires without confirmation → raises `ConfirmationTimeout`, agent receives an error tool result and can reason about it

The loop's cancellation check (`_raise_if_canceled`) runs before and after the confirmation wait.

---

## System Prompt Changes

The system prompt's data sourcing section changes from:

> "1. fetch_data — pull WTI (CL=F), DXY (DX-Y.NYB), XLE, SPY and INDPRO"

To:

> "1. list_data_sources — discover what data connectors are available and which are blocked.
>  2. fetch_from_source — for each available source relevant to the analysis, fetch the data. Mention any blocked sources and why they couldn't be included."

The agent now reasons about what data would be useful for the task and chooses what to pull, rather than executing a fixed list.

---

## User-Extensible Connectors

A user adding a custom connector creates:

```
backend/src/data/connectors/my_source/
├── manifest.yaml
└── connector.py
```

No code changes to the registry, tools, or loop are needed. The registry auto-discovers it on next startup. If `requires_env` names a key that is present in `.env`, the connector becomes available immediately.

For the initial implementation, connector addition is file-based only (no UI). A future session can add a UI for registering connectors mid-session via the API.

---

## File Map

| Action | Path | What changes |
|--------|------|--------------|
| Create | `backend/src/data/registry.py` | `ConnectorRegistry` class |
| Create | `backend/src/data/connectors/yfinance/manifest.yaml` | yfinance manifest |
| Create | `backend/src/data/connectors/yfinance/connector.py` | yfinance fetch() |
| Create | `backend/src/data/connectors/fred/manifest.yaml` | FRED manifest |
| Create | `backend/src/data/connectors/fred/connector.py` | FRED fetch() |
| Create | `backend/src/data/connectors/gpr/manifest.yaml` | GPR manifest |
| Create | `backend/src/data/connectors/gpr/connector.py` | GPR fetch() |
| Create | `backend/src/data/connectors/eia/manifest.yaml` | EIA manifest |
| Create | `backend/src/data/connectors/eia/connector.py` | EIA fetch() |
| Modify | `backend/src/agent/tools.py` | Replace `fetch_data` with `list_data_sources` + `fetch_from_source` |
| Modify | `backend/src/agent/loop.py` | Update system prompt data sourcing section |
| Modify | `backend/src/data/__init__.py` | Export `connector_registry` singleton |
| Delete | `backend/src/data/connectors.py` | Replaced by registry + per-connector modules (existing fetch logic migrated into connector.py files) |
| Create | `backend/tests/test_connector_registry.py` | Registry unit tests |
| Create | `backend/tests/test_data_tools.py` | Tool function tests |

---

## Testing

| Test | What it checks |
|------|---------------|
| `test_registry_scans_manifests` | Registry finds all 4 built-in connectors after scan |
| `test_registry_available_when_key_present` | FRED appears in `available` when `FRED_API_KEY` is set |
| `test_registry_blocked_when_key_missing` | FRED appears in `blocked` with reason when key absent |
| `test_registry_unknown_connector_raises` | `fetch("nonexistent", ...)` raises `KeyError` |
| `test_user_connector_auto_discovered` | Dropping a manifest into a temp dir makes it appear in list |
| `test_list_data_sources_tool` | Tool returns correct shape; `available`/`blocked` keys present |
| `test_fetch_from_source_dispatches` | `fetch_from_source("yfinance", {...})` calls connector's fetch() |
| `test_fetch_from_source_blocked_source` | Returns error dict rather than raising |
| `test_fetch_from_source_invalid_params` | Returns validation error dict |

Confirmation gate (Tier 4) is tested with a mock Redis that immediately resolves the blpop.

---

## Out of Scope

- Frontend UI for the `confirmation_required` WebSocket event (backend emits it; frontend handling is a separate session)
- Connector marketplace or remote connector registry
- Per-user connector isolation or sandboxing of user-provided code
