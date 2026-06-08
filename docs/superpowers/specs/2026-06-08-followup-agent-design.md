# FollowUpAgent — Design

## Context

`ExplanationAgent` (PR 4a, merged) advances sessions from `EXPLAINING` into `FOLLOW_UP` and
sets `status = WAITING`. At that point the session is parked waiting for the user's next
message — but `POST /sessions/{id}/chat` only accepts messages while
`stage in _CHAT_ALLOWED_STAGES`, which today is just `{USER_REVIEW}`
(`backend/api/routes/chat.py:25`). There is no agent that can answer follow-up questions about
the analysis or act on requests to change settings and re-run.

This spec implements `FollowUpAgent` — the LLM agent that handles `FOLLOW_UP`-stage chat — and
extends `chat.py` to route messages to it. It is the deferred half of the original "PR 4-backend"
scope (see `docs/backend-redesign.md`'s split of PR 4 into 4a/4b).

Two pieces of existing machinery this design builds on:
- `BaseAgent.run()` executes tool functions **synchronously** (`backend/src/agents/base.py:102`,
  `result = entry.fn(**args, context=context)`, not awaited) and, when a tool is registered with
  `is_stop=True`, returns `json.dumps(result)` immediately as the final output
  (`backend/src/agents/base.py:115`, the same mechanism `DataAgent.complete()` uses).
- `tabpfn._run` already chains a follow-on background service by directly `await`-ing it after
  committing its own stage transition (`await run_explanation_service(session_id, engine)`,
  `backend/src/services/tabpfn.py:171,266`) — the template this design reuses for chaining
  re-runs, since a background-task function has no `BackgroundTasks` object to dispatch through.

## Goals

- Let the user ask follow-up questions about the regime/direction/drift findings, the data and
  featurizer settings, and how this session compares to a similar prior one — answered directly
  from the session's own data, in natural language, streamed over the existing WebSocket
  activity feed.
- Let the user ask to change featurizer settings or pull in additional data sources, and have
  the agent trigger the appropriate stage regression (`FEATURIZING` or `DATA_GATHERING`) and
  re-run the pipeline from there — while still giving the user an immediate natural-language
  acknowledgement of what's about to happen.
- Wire `POST /sessions/{id}/chat` to accept messages at the `FOLLOW_UP` stage and dispatch them
  to `FollowUpAgent` via a background task (mirroring how `ExplanationAgent` and `DataAgent` run
  as background services, not inline in the request).

## Non-goals

- Computing SHAP feature-importance or backtest results — these `AnalysisResult` columns are
  still never populated anywhere (same non-goal `ExplanationAgent` carries forward). The agent
  must say plainly that this data isn't available if asked, never invent it.
- A dedicated `compare_sessions` or `explain_feature` tool. Both are folded directly into the
  agent's pre-built context block (see Architecture) — `compare_sessions` because its target is
  fully deterministic from the current session's `market_profile`, and `explain_feature` because
  it would only ever report on data (SHAP) that doesn't exist.
- Any new REST endpoints, request/response model changes, or `BaseAgent` changes. The two rerun
  tools fit entirely within the existing synchronous-tool / `is_stop` mechanism.
- Reworking `POST /rerun`'s existing `BackgroundTasks`-based dispatch in `pipeline.py`. It stays
  as-is for the explicit user-initiated rerun-from-`USER_REVIEW`-config-screen flow;
  `FollowUpAgent`'s chat-driven reruns use a parallel, simpler in-place `await` chain (see
  Architecture) because a background-task function has no `BackgroundTasks` to dispatch through.

## Architecture

### New files

**`backend/src/agents/followup_agent.py`** — `make_followup_agent() -> BaseAgent`, mirroring
`make_data_agent()`'s factory shape (system prompt + two registered tools, both `is_stop=True`):

```python
def make_followup_agent() -> BaseAgent:
    agent = BaseAgent(name="FollowUpAgent", system_prompt=_SYSTEM_PROMPT)

    def rerun_featurizer(
        featurizer_config_patch: dict[str, Any], reply: str, context: AgentContext | None = None
    ) -> dict[str, Any]:
        """Patch the featurizer config and re-run featurizing (and downstream analysis)."""
        return {
            "action": "rerun",
            "stage": "featurizing",
            "patch": featurizer_config_patch,
            "reply": reply,
        }

    def rerun_data_gathering(
        sources_to_add: list[str], reply: str, context: AgentContext | None = None
    ) -> dict[str, Any]:
        """Add data sources and re-run the full pipeline from data gathering."""
        return {
            "action": "rerun",
            "stage": "data_gathering",
            "sources_to_add": sources_to_add,
            "reply": reply,
        }

    agent.register_tool(
        rerun_featurizer,
        {
            "type": "object",
            "properties": {
                "featurizer_config_patch": {
                    "type": "object",
                    "description": "Partial featurizer_config to merge in, e.g. {\"windows\": [5, 30, 90]}",
                },
                "reply": {
                    "type": "string",
                    "description": "Short natural-language confirmation of what you're about to do",
                },
            },
            "required": ["featurizer_config_patch", "reply"],
        },
        is_stop=True,
    )
    agent.register_tool(
        rerun_data_gathering,
        {
            "type": "object",
            "properties": {
                "sources_to_add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Natural-language descriptions of data sources to add, e.g. \"Brent crude futures\"",
                },
                "reply": {
                    "type": "string",
                    "description": "Short natural-language confirmation of what you're about to do",
                },
            },
            "required": ["sources_to_add", "reply"],
        },
        is_stop=True,
    )
    return agent
```

`sources_to_add` carries natural-language descriptions, not connector IDs — the same shape
`ReviewInterpreter`'s `refetch` action already produces (`updates.sources_to_add`, consumed by
`chat.py`'s existing `refetch` branch as raw strings passed straight into `pending_sources`).
`run_followup_service` resolves them downstream the same way.

Both tools are `is_stop=True`: when the agent decides to act, `BaseAgent.run()` returns
`json.dumps({...})` immediately — the **only** return value `run_followup_service` ever sees, so
the tool itself must carry both the regression parameters *and* a user-facing `reply` string in
one LLM round-trip (there is no second chance for the agent to produce follow-up text after a
stop tool fires). `reply` is a required argument on both schemas specifically to guarantee this.

**System prompt** (`_SYSTEM_PROMPT`) instructs the model to:
- Answer questions about the regime call, direction call, drift findings, data sources, and
  featurizer settings directly and tersely from the supplied context block — no tool call needed
  for these.
- Answer comparison questions ("how does this compare to last time?") using the pre-fetched
  comparable-session block in the context — and say plainly if none is available
  (`{"available": false}`).
- State plainly that feature-importance (SHAP) and backtest data are not available if asked —
  never invent commentary about data that wasn't supplied (same "never invent" rule
  `ExplanationAgent` carries).
- Call `rerun_featurizer` or `rerun_data_gathering` **only** when the user clearly asks to change
  settings or add data sources — and always include a short, friendly `reply` confirming what's
  about to happen, since that `reply` is the only text the user will see for this turn.

Uses `settings.agent_model` (the full model, like `DataAgent`/`ExplanationAgent` — this involves
judgment calls about intent, not cheap classification).

**`backend/src/services/followup.py`** — `run_followup_service(session_id, engine)`, following
the exact background-service shape of `run_explanation_service`
(`backend/src/services/explanation.py:25`): builds the `publisher` closure
(`channel = f"session:{session_id}:stream"`), guards on session-not-found /
`status == CANCELED` / `stage != FOLLOW_UP`, wraps `_run` in try/except → `FAILED`.

```python
async def run_followup_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    session_id_str = str(session_id)
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{session_id_str}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        async with AsyncSession(engine) as db:
            s = await db.get(SessionModel, session_id)
            if s is None:
                return
            if s.status == SessionStatus.CANCELED:
                return
            if s.stage != SessionStage.FOLLOW_UP:
                return
            try:
                await _run(s, db, engine, publisher)
            except Exception as exc:
                set_status(s, SessionStatus.FAILED, error=str(exc))
                err_event = {"type": "error", "stage": "follow_up", "message": str(exc)}
                append_activity_event(s, err_event)
                await db.commit()
                await publisher(err_event)
    finally:
        await r.aclose()
```

`_build_followup_context_block(...)` mirrors `_build_context_block`
(`backend/src/services/explanation.py:64`) — same shape, with two additions: the pre-fetched
**comparable session** block, and the triggering user message.

```python
def _build_followup_context_block(
    regime, direction, drift, feature_importance, backtest,
    data_manifest, featurizer_config, conversation, comparable_session,
) -> str:
    prior_turns = conversation[-6:]
    history = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in prior_turns)
    return (
        f"Regime result: {json.dumps(regime)}\n"
        f"Direction result: {json.dumps(direction)}\n"
        f"Drift result: {json.dumps(drift)}\n"
        f"Feature importance (SHAP): {json.dumps(feature_importance)}\n"
        f"Backtest result: {json.dumps(backtest)}\n"
        f"Data manifest: {json.dumps(data_manifest)}\n"
        f"Featurizer config: {json.dumps(featurizer_config)}\n"
        f"Comparable prior session: {json.dumps(comparable_session)}\n"
        f"Recent conversation:\n{history}\n"
        "Respond to the user's latest message now."
    )
```

`comparable_session` is looked up deterministically before the agent runs — "most recent *other*
session with the same `market_profile`, `stage == FOLLOW_UP`, `id != current`" — and shaped as
`{"available": True, "regime": ..., "direction": ..., "summary": ..., "timeframe": {"start": ...,
"end": ...}}` or `{"available": False}` if none exists. This is a plain `select(...)
.where(...).order_by(SessionModel.created_at.desc()).limit(1)` query against `SessionModel` and
its latest `AnalysisResult` — no tool call, no LLM judgment involved.

`_run` flow (publisher, snapshot-before-await, and re-fetch-after-await all following the exact
pattern of `explanation._run`):

1. Snapshot `conversation`, `featurizer_config`, `pending_sources` from `s` before the first
   `await` (the `data_gathering` regression branch below needs `current_pending` to build the
   merged `pending_sources` list — same snapshot-before-await discipline `chat.py:76` already
   follows for the identical merge).
2. Fetch the latest `AnalysisResult` (for `regime`/`direction`/`drift`/`feature_importance`/
   `backtest`), latest `DataArtifact` (for `data_manifest`), and the comparable session.
3. Build the context block, call
   `await agent.run(context=None, publisher=publisher, initial_user_message=context_block)`.
4. Re-fetch the session fresh (asyncpg-expiry + cancellation guard, same as `explanation._run`
   step 5): if `None` or `CANCELED`, log `followup.canceled_midrun` and return — no writes, no
   regression.
5. Parse the agent's returned JSON string:
   - **Not valid JSON / no `action` key** → it's a plain-text answer. Append
     `{"role": "assistant", "content": <text>, "created_at": ...}` to `conversation`, append a
     `chat_reply` activity event, `set_status(WAITING)`, commit, publish the `chat_reply` event.
   - **`{"action": "rerun", "stage": ..., "reply": ..., ...}`** → append
     `{"role": "assistant", "content": intent["reply"], ...}` to `conversation` and a
     `chat_reply` activity event, commit **immediately** (so the user sees the acknowledgement
     before the — possibly slow — rerun starts), then perform the regression:
     - `featurizing`: `s.featurizer_config = apply_config_patch(current_featurizer_config,
       intent["patch"])`, `transition_stage(s, SessionStage.FEATURIZING)`,
       `set_status(s, SessionStatus.RUNNING)`, commit, publish `stage_transition`, then
       `await run_featurizer_service(session_id, engine)` → `await
       run_tabpfn_service(session_id, engine)`
     - `data_gathering`: `s.pending_sources = [*current_pending, *[{"connector_id": sid,
       "params": {}} for sid in intent["sources_to_add"]]]` (same shape `chat.py`'s `refetch`
       branch already builds), `transition_stage(s, SessionStage.DATA_GATHERING)`,
       `set_status(s, SessionStatus.RUNNING)`, commit, publish `stage_transition`, then
       `await run_data_agent_service(session_id, engine)` → `await
       run_featurizer_service(session_id, engine)` → `await run_tabpfn_service(session_id,
       engine)`

   Both regression branches use `apply_config_patch` for the featurizer-config merge — the
   helper `chat.py`'s `update_config` action already uses
   (`backend/src/services/featurizer_config.py`) — rather than `pipeline.py`'s raw
   `{**s.featurizer_config, **patch}` merge in `POST /rerun`, since this is new code with no
   reason to repeat that inconsistency.

### Wiring change in `chat.py`

`_CHAT_ALLOWED_STAGES` extends from `{SessionStage.USER_REVIEW.value}` to
`{SessionStage.USER_REVIEW.value, SessionStage.FOLLOW_UP.value}`.

The handler gains a stage check immediately after the existing `_CHAT_ALLOWED_STAGES` gate
(`backend/api/routes/chat.py:66-67`), branching *before* the `ReviewInterpreter` call — `FOLLOW_UP`
messages never go through `ReviewInterpreter`; the agent itself decides whether to answer or act:

```python
if s.stage == SessionStage.FOLLOW_UP.value:
    _req_time = datetime.now(UTC).isoformat()
    s.conversation = [
        *s.conversation,
        {"role": "user", "content": req.message, "created_at": _req_time},
    ]
    s.status = SessionStatus.RUNNING.value
    await db.commit()
    background_tasks.add_task(run_followup_service, uid, engine)
    return ChatResponse(session_id=session_id)
```

This sits as a sibling fork to the existing `USER_REVIEW`/`ReviewInterpreter` path — the rest of
`chat()` (snapshotting, `ReviewInterpreter.interpret`, the `advance`/`refetch`/`update_config`/
`answer` branches) is untouched and continues to serve `USER_REVIEW` exactly as today. No
changes to `ChatRequest`/`ChatResponse` (`backend/api/models.py:166-171`) — `FOLLOW_UP` always
treats the body as free-text `message`.

## Data flow

```
FOLLOW_UP, status = WAITING (ExplanationAgent parked here)
   → user sends POST /sessions/{id}/chat  {"message": "..."}
   → chat.py: append user message, status = RUNNING, commit, return 202
   → background_tasks.add_task(run_followup_service, session_id, engine)

run_followup_service:
   → loads AnalysisResult + DataArtifact + comparable prior session
   → FollowUpAgent.run() — one LLM call, streamed as `thought`/`tool_call`/`tool_result` events
   → branch on returned JSON:

   plain-text answer                          rerun intent ({"action": "rerun", ...})
   ──────────────────                         ──────────────────────────────────────
   append assistant reply to conversation     append assistant `reply` to conversation
   publish `chat_reply`                       publish `chat_reply`, commit
   status = WAITING                           transition_stage → FEATURIZING|DATA_GATHERING
   (stays in FOLLOW_UP)                       status = RUNNING, publish `stage_transition`
                                               await chain:
                                                 featurizing: featurizer → tabpfn
                                                 data_gathering: data_agent → featurizer → tabpfn
                                               (chain ultimately reaches EXPLAINING → FOLLOW_UP
                                                again, parking the session for the next message)
```

## Error handling

- Pre-flight guards (session not found / `CANCELED` / `stage != FOLLOW_UP`) → silent return, no
  error event — these are "arrived too late" races, not failures, matching every existing
  background service's guard pattern.
- Mid-run cancellation (after the LLM `await`, before any write) → log
  `followup.canceled_midrun` and return without writing the reply or performing any regression —
  same guarantee `explanation._run`'s `test_run_explanation_service_skips_write_when_canceled_midrun`
  encodes.
- Any other exception anywhere in `_run` — including partway through a rerun chain (e.g.
  `run_featurizer_service` raising) — is caught by `run_followup_service`'s single outer
  try/except: `status = FAILED`, `error = str(exc)`, an `error` activity event with
  `stage: "follow_up"`, committed and published. No special unwinding of a partially-completed
  chain — this matches how `tabpfn._run`'s existing `await run_explanation_service(...)` chain
  call behaves today (an exception there isn't separately caught either; it propagates to
  `run_tabpfn_service`'s outer handler).

## Testing

**`backend/tests/test_followup_agent.py`** — unit tests for `make_followup_agent()`: returns a
`BaseAgent` named `"FollowUpAgent"` with exactly `rerun_featurizer` and `rerun_data_gathering`
registered, both `is_stop=True`; the system prompt mentions handling missing SHAP/backtest data
gracefully and instructs always including `reply` when calling a rerun tool.

**`backend/tests/test_followup_service.py`** — service-level tests, mocking
`src.agents.base.openai.AsyncOpenAI` (same mocking point as `test_explanation_service.py`) with
helpers `_text_resp` (plain-text answer) and a new `_tool_call_resp(name, arguments)` (stop-tool
response shaped like the mocked client returns for `DataAgent`/`ReviewInterpreter` tool-call
tests), plus `_FakeRedis`/`_make_engine`/`_seed_session` mirroring `test_explanation_service.py`:

- stage/status guards short-circuit when `stage != FOLLOW_UP` or session is `CANCELED`
- a plain-text response: reply appended to `conversation`, `chat_reply` activity event +
  publish, `status` set to `WAITING`, stage stays `FOLLOW_UP`
- a `rerun_featurizer` tool-call response: reply appended to `conversation` *before* the
  regression; `featurizer_config` patched via `apply_config_patch`; stage transitions
  `FOLLOW_UP → FEATURIZING`, `status = RUNNING`; `run_featurizer_service` and
  `run_tabpfn_service` mocked as `AsyncMock` and asserted `assert_awaited_once_with(session_id,
  engine)` in order
- a `rerun_data_gathering` tool-call response: same shape, `pending_sources` populated from
  `sources_to_add`, stage transitions to `DATA_GATHERING`, and the three-stage chain
  (`run_data_agent_service` → `run_featurizer_service` → `run_tabpfn_service`) is awaited in
  order
- the mid-run cancellation guard short-circuits without writing the reply or starting any
  regression (`conversation` unchanged, no chain mocks called)
- an exception during the agent call (or during a chained service call) results in
  `status = FAILED`, `error` set, and an `error` activity event with `stage: "follow_up"`

**`backend/tests/test_chat.py`** — extend with a `FOLLOW_UP`-stage case: posting a message at
`stage = FOLLOW_UP` returns `202`, appends the user message to `conversation`, sets
`status = RUNNING`, and enqueues `run_followup_service` (assert via mocking
`BackgroundTasks.add_task`, the same way `test_chat.py`'s existing `advance`/`refetch` cases
assert `_run_featurizer_background`/`_run_data_agent_background` are enqueued) — and that it does
**not** invoke `ReviewInterpreter`.

## Open questions

None — all prior ambiguities (tool/intent shape, `compare_sessions`/`explain_feature` scope,
chat routing, chaining mechanism, reply+intent round-trip, error handling) were resolved during
brainstorming and are reflected above as decisions.
