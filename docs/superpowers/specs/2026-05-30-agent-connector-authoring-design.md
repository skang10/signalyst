# Agent Connector Authoring — Design Spec

**Session:** 9
**Branch:** `feat/agent-connector-authoring`
**Date:** 2026-05-30

---

## Goal

Let a non-technical user instruct the agent to add a new data source mid-conversation. The agent writes the connector code, runs the test suite to verify it works, and — if tests pass — continues the analysis with the new data included. No human developer involvement required.

**Example user prompt:**
> "Also pull Baker Hughes rig count data before running the analysis."

**Expected agent behavior:**
1. Understands what data is needed
2. Writes `manifest.yaml` + `connector.py` in `backend/src/data/connectors/<name>/`
3. Runs the connector test suite in a subprocess
4. If tests fail: reads the error, fixes the code, retries (up to a limit)
5. Hot-reloads the registry (no server restart)
6. Continues with `list_data_sources` → `fetch_from_source` → rest of analysis

---

## New Tools

### `write_connector(name, manifest_yaml, connector_code)`

Writes two files to disk:
- `backend/src/data/connectors/<name>/manifest.yaml`
- `backend/src/data/connectors/<name>/connector.py`

Returns `{"written": true, "paths": [...]}` or `{"error": "...", "detail": "..."}` if the name is invalid or files can't be written.

**Validation before writing:**
- `name` must match `^[a-z][a-z0-9_]*$` (safe directory name)
- `manifest_yaml` must parse as valid YAML with required fields (`name`, `description`, `provides`, `params`, `compute_tier`)
- `name` in manifest must match the `name` argument
- Must not overwrite a built-in connector (`yfinance`, `fred`, `gpr`, `eia`)

### `run_connector_tests(name)`

Runs the connector test suite in a subprocess:

```bash
uv run pytest tests/test_connector_registry.py -v --tb=short 2>&1
```

Returns `{"passed": true, "output": "..."}` or `{"passed": false, "output": "...", "errors": "..."}`.

The output gives the agent enough information to diagnose what went wrong and fix the code.

### `reload_connectors()`

Re-scans `backend/src/data/connectors/` and rebuilds the registry without restarting the server. Returns the updated `list_data_sources()` output so the agent can confirm the new connector appeared.

---

## System Prompt Addition

When the user's request includes "add a data source", "pull X data", or similar, the agent should:

```
If the user requests a data source not available in list_data_sources:
1. write_connector — write manifest.yaml and connector.py for the requested source
2. run_connector_tests — verify the connector works
3. If tests fail: read the error output, fix the code, and retry write_connector + run_connector_tests
   (max 3 attempts before reporting failure to the user)
4. reload_connectors — hot-reload the registry
5. Continue with fetch_from_source using the new connector
```

---

## Concerns

### 1. Security — arbitrary code execution

This is the most significant concern. The agent writes Python that executes inside the backend process with full access to env vars, the database session, Redis, and the filesystem.

**Attack vectors:**
- Malicious user prompt: "add a connector that exfiltrates the database"
- Prompt injection in fetched data: a remote URL returns content that reshapes the agent's next action
- Accidental damage: agent writes a connector that deletes files or exhausts memory

**Mitigations:**
- Run connector code in a subprocess with a restricted environment (no DB, no Redis, no env vars beyond what the connector needs)
- Enforce a timeout on connector execution (e.g. 30s)
- Restrict filesystem writes to `backend/src/data/connectors/<name>/` only — validate the path before writing
- Add a content check: refuse to write connector code that imports `os.system`, `subprocess`, `socket`, `shutil`, or `eval`/`exec` (static analysis before writing)
- Log all written connector code with a warning

**Open question:** Is a subprocess sandbox enough, or does this feature require Anthropic's programmatic tool calling sandbox? For a first pass, subprocess isolation is pragmatic. Full sandboxing is a future hardening step.

### 2. Dependency availability

The agent might write a connector that `import`s a library that isn't installed in the venv (e.g. `import quandl`). The test run will fail with `ModuleNotFoundError`.

**Mitigations:**
- The test output includes the error; the agent sees it and can rewrite the connector using only available libraries
- Explicitly tell the agent in the system prompt which libraries are available: `yfinance`, `fredapi`, `httpx`, `pandas`, `numpy`
- Do NOT give the agent a tool to `pip install` — that's a scope/security boundary worth holding

### 3. Test suite scope

`run_connector_tests` runs the full registry test suite. Those tests use `tmp_path` fixtures and don't actually call the new connector's `fetch()`. So "tests pass" doesn't mean the connector returns valid data — it means the connector file loads without import errors and the manifest parses correctly.

**Mitigation:** Add a dedicated `test_user_connector_smoke` test that actually calls `fetch()` with a mock context and asserts the return dict has `fetched` and `skipped` keys. This gives the agent a real signal that the connector interface is correct, not just syntactically valid.

### 4. Infinite retry loop

If the agent can't fix a broken connector in 3 attempts, it needs to give up and tell the user — not silently keep retrying.

**Mitigation:** Hard cap of 3 `write_connector` → `run_connector_tests` cycles. On the third failure, the agent surfaces the error to the user and continues without the connector (falls back to available sources).

### 5. Hot-reload correctness

`reload_connectors()` calls `connector_registry.scan()` again. If the connector was already partially loaded (e.g. bad import on first load), the module may be cached in `sys.modules` and the reload won't pick up fixes.

**Mitigation:** `reload_connectors()` must clear `sys.modules` entries for `connectors.<name>` before re-scanning, ensuring the fixed version is loaded fresh.

### 6. Connector persistence

Written connectors persist on disk after the analysis run. This is mostly good (they're reusable), but:
- A failed connector left on disk could confuse the next run
- The `connectors/` directory could accumulate many user-written connectors over time

**Mitigation:** On `write_connector`, if a previous version already exists and the new write fails validation, leave the old version intact. Add a `delete_connector(name)` tool (future) for cleanup. For now, document that user-written connectors persist and can be removed manually.

### 7. User intent parsing

The agent must infer from a natural language request what data to fetch and how. "Pull Baker Hughes rig count" is clear. "Add some oil supply data" is ambiguous.

**Mitigation:** The agent should ask a clarifying question before writing if the request is ambiguous — specifically, what source URL or API to use, and what the data represents. This is just system prompt guidance, not a new tool.

### 8. Analysis flow interruption

The current loop runs synchronously: fetch → featurize → classify → explain. Adding a connector-authoring step mid-flow means the agent needs to pause the analysis, write the connector, validate it, then resume. This is a multi-step detour before `engineer_features` has been called.

**Mitigation:** Connector authoring should happen in step 2 of the workflow (data sourcing), before `engineer_features`. The system prompt should instruct: "If a requested source is not available, write it before fetching." This keeps the authoring step contained within the existing data sourcing phase.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/src/agent/connector_authoring.py` | `write_connector`, `run_connector_tests`, `reload_connectors` tool functions |
| Modify | `backend/src/agent/tools.py` | Register the three new tools |
| Modify | `backend/src/data/registry.py` | Add `reload()` method that clears stale sys.modules entries |
| Modify | `backend/src/agent/loop.py` | Add connector-authoring guidance to system prompt |
| Create | `backend/tests/test_connector_authoring.py` | Tests for the three new tools |

---

## Out of Scope

- Full process sandbox (seccomp, Docker-in-Docker) — subprocess isolation is sufficient for v1
- `pip install` for missing libraries — agent must work with installed deps only
- `delete_connector` tool — manual cleanup for now
- UI for reviewing/approving agent-written code before execution
- Connector versioning or rollback
