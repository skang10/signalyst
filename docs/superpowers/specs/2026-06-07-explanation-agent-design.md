# ExplanationAgent — Design

## Context

The documented stage machine is `CONFIGURING → DATA_GATHERING → USER_REVIEW → FEATURIZING →
ANALYZING → EXPLAINING → FOLLOW_UP`. Today the pipeline skips `EXPLAINING` entirely —
`backend/src/services/tabpfn.py` transitions straight from `ANALYZING` to `FOLLOW_UP` in both
its cache-hit branch and its fresh-analysis branch, with a marker comment:

```python
# PR 2: skip EXPLAINING (ExplanationAgent is PR 4), go straight to FOLLOW_UP
```

This plan implements `ExplanationAgent`, the LLM agent (no tools) that generates a
natural-language summary of the analysis and writes it to `AnalysisResult.summary`, and wires
it into the pipeline so `EXPLAINING` actually runs. It is the smaller half of the documented
"PR 4-backend" scope; `FollowUpAgent` (and extending `POST /chat` to the `FOLLOW_UP` stage)
is deliberately out of scope here and will be its own follow-up spec. The
`GET /api/sessions/{id}/artifacts/{artifact_id}` endpoint mentioned in the PR 4 description is
already implemented (`backend/api/routes/pipeline.py:470`, with tests in `test_pipeline.py`) —
nothing further is needed there.

## Goals

- Generate a natural-language summary of the regime/direction/drift findings, the data and
  featurizer settings used, and relevant conversation context.
- Write that summary into `AnalysisResult.summary` and stream the agent's reasoning to the
  frontend over the existing WebSocket activity stream.
- Make `EXPLAINING → FOLLOW_UP` an unconditional step that always runs after `ANALYZING`,
  whether the `AnalysisResult` was freshly computed or reused via the within-session cache
  ("always re-runs — even on full cache hit", per `docs/backend-redesign.md`).

## Non-goals

- Computing SHAP feature-importance or backtest results. These `AnalysisResult` columns exist
  but are never populated anywhere in the codebase today — adding that computation is a
  separate, much larger inference feature. The agent must handle their absence gracefully
  (omit those sections rather than fabricating commentary).
- `FollowUpAgent`, extending `POST /chat` to `FOLLOW_UP`, or any chat-driven stage regression —
  separate spec.
- Any new REST endpoints — the artifact-detail endpoint already exists.

## Architecture

### New files

**`backend/src/agents/explanation_agent.py`** — `make_explanation_agent() -> BaseAgent`,
mirroring `make_data_agent()` / `make_discovery_agent()`:

```python
def make_explanation_agent() -> BaseAgent:
    return BaseAgent(name="ExplanationAgent", system_prompt=_SYSTEM_PROMPT)
```

No tools are registered. `BaseAgent.run()` makes one LLM call; since the response has no
`tool_calls`, the loop streams the response as a `{"type": "thought", ...}` event via the
publisher and returns the text on the first iteration. That returned string is the summary.

Uses `settings.agent_model` (the full model — like `DataAgent`/`DiscoveryAgent`, not
`agent_model_fast`), since this is substantive natural-language synthesis, not cheap
classification.

**System prompt** instructs the model to write an analyst-style summary covering:
- the regime call and confidence, and the price-direction call and confidence
- drift findings (whether drift was detected, drifted features, PSI score)
- the data sources used (from `data_manifest`) and featurizer settings (`featurizer_config`)
- relevant context from the conversation (e.g., if the user adjusted settings or asked about
  specific tickers during review, acknowledge how the analysis reflects that)
- explicit instruction to only discuss feature-importance/backtest findings *if present* in the
  supplied data — never invent commentary about data that wasn't provided

**`backend/src/services/explanation.py`** — `run_explanation_service(session_id, engine)`,
following the `discovery.py` / `tabpfn.py` background-service shape:

```python
async def run_explanation_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None or s.status == SessionStatus.CANCELED:
            return
        if s.stage != SessionStage.EXPLAINING:
            return
        await _run(s, db, engine)
```

Inside `_run` (publisher closure built here, channel `f"session:{session_id}:stream"`,
wrapped in try/except → `FAILED`, matching `tabpfn.run_tabpfn_service`):

1. Snapshot `conversation`, `featurizer_config`, `activity_events`, `stage_history` from `s`
   before any `await` (asyncpg expires the object across the connection-pool boundary).
2. Look up the **current** `AnalysisResult` for this session (most recent by `created_at`) and
   the latest `DataArtifact` for `data_manifest` — read-only queries, no expiry risk yet.
3. Assemble the `initial_user_message` context block: `regime`, `direction`, `drift`,
   `feature_importance`, `backtest` from the `AnalysisResult` (whichever fields are non-null);
   `data_manifest`; `featurizer_config`; the last ~6 conversation turns (same windowing
   convention as `ReviewInterpreter.interpret`).
4. Build the agent and call
   `await agent.run(context=None, publisher=publisher, initial_user_message=<context block>)`.
5. After the `await`, `s` is expired — re-fetch `s` and the `AnalysisResult` row fresh.
   **Cancellation guard**: if the re-fetched session is `None` or `status == CANCELED`, log and
   return without writing anything (mirrors the guard in `tabpfn._run` between inference and
   commit — the LLM round-trip is long enough that a user could cancel mid-explanation).
6. Otherwise: set `analysis_result.summary = <agent output>`, append a `summary_ready`
   activity event (`{"type": "artifact_ready", "kind": "analysis_summary", "artifact_id":
   str(analysis_result.id)}` — extends the existing `artifact_ready` convention with a new
   `kind`), `transition_stage(s, SessionStage.FOLLOW_UP)`, `set_status(s, SessionStatus.WAITING)`,
   commit, then publish the `summary_ready` event and a
   `{"type": "stage_transition", "from": "explaining", "to": "follow_up"}` event.
7. On exception: `set_status(s, SessionStatus.FAILED, error=str(exc))`, append an `error`
   activity event (`stage: "explaining"`), commit, publish — same shape as
   `tabpfn.run_tabpfn_service`'s except-block.

### Wiring change in `tabpfn.py`

Both places `_run` currently transitions straight to `FOLLOW_UP` become a transition to
`EXPLAINING` followed by a chained call to the new service — this is the single edit point that
guarantees `EXPLAINING` always runs after `ANALYZING`, regardless of which of the six
background-task call chains triggered the pipeline (since `EXPLAINING` is not an optional,
orchestration-layer choice but a fixed step in the stage machine):

- **Cache-hit branch** (~line 166): `transition_stage(s, SessionStage.FOLLOW_UP)` →
  `transition_stage(s, SessionStage.EXPLAINING)`; the published event becomes
  `{"type": "stage_transition", "from": "analyzing", "to": "explaining"}`; then
  `await run_explanation_service(session_id, engine)`.
- **Fresh-analysis branch** (~line 261): same swap — `transition_stage(s,
  SessionStage.EXPLAINING)`, then `await run_explanation_service(session_id, engine)`. The
  `# PR 2: skip EXPLAINING...` comment is removed, since this change is its resolution.
- Import `run_explanation_service` using the same lazy/local-import convention `tabpfn.py`
  already uses for chained service calls (to avoid circular imports between `services` modules).

## Data flow

```
ANALYZING (tabpfn._run completes or cache-hits)
   → transition_stage(EXPLAINING)
   → run_explanation_service
        → loads AnalysisResult + DataArtifact + session conversation/config
        → ExplanationAgent.run() — single LLM call, streamed as `thought` events
        → writes AnalysisResult.summary
        → publishes `artifact_ready` (kind: analysis_summary) + `stage_transition`
        → transition_stage(FOLLOW_UP), set_status(WAITING)
   → FOLLOW_UP (session now WAITING for the next /chat — handled by a future FollowUpAgent spec)
```

## Error handling

- Session not found / canceled / wrong stage at entry → silent return (matches every existing
  background service's guard pattern).
- Mid-run cancellation (after the LLM call returns, before commit) → silent return, no summary
  written, no stage transition — the session stays wherever the cancel handler left it.
- Any other exception during the run → `status = FAILED`, `error = str(exc)`, an `error`
  activity event with `stage: "explaining"`, committed and published — identical shape to
  `tabpfn.run_tabpfn_service`'s except-block.

## Testing

- **`tests/test_explanation_agent.py`** — unit tests for `make_explanation_agent()`: returns a
  `BaseAgent` named `"ExplanationAgent"` with no tools registered (`agent._tools == {}`), and
  the system prompt mentions handling missing SHAP/backtest data gracefully.
- **`tests/test_explanation_service.py`** — service-level tests mocking
  `src.agents.base.openai.AsyncOpenAI` (the same mocking point `test_data_agent.py` and
  `test_discovery_agent.py` use), covering:
  - stage/status guards short-circuit when stage != EXPLAINING or session is canceled
  - a normal run writes `AnalysisResult.summary`, appends `summary_ready` +
    `stage_transition` activity events, transitions `EXPLAINING → FOLLOW_UP`, and sets
    status to `WAITING`
  - the mid-run cancellation guard short-circuits without writing a summary or transitioning
  - an exception during the agent call results in `status = FAILED`, `error` set, and an
    `error` activity event with `stage: "explaining"`
- **`tests/test_pipeline.py`** — extend the existing end-to-end pipeline test(s) (the ones that
  currently assert the chain reaches `FOLLOW_UP`) to assert the session passes through
  `EXPLAINING` first — e.g., check `stage_history` contains an `explaining` entry before the
  `follow_up` entry, and that `AnalysisResult.summary` is non-null at the end — with the OpenAI
  client mocked the same way `test_chat.py`/`test_pipeline.py` mock chained background-task
  functions (`patch(..., new_callable=AsyncMock)`).

## Open questions

None — all prior ambiguities (agent shape, chaining location, missing SHAP/backtest handling,
cancellation guard) were resolved during brainstorming and are reflected above as decisions.
