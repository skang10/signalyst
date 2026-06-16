# Summary Agent Improvements — Design

## Background

The Overview tab (added in #75) already shows the regime call, direction call, confidence levels, drift/PSI score, and top SHAP feature as stat tiles and distribution bars. The `ExplanationAgent` (`backend/src/agents/explanation_agent.py`) generates a free-text `summary` (4 paragraphs) that largely restates these same numbers, and the frontend renders it as a single plain-text paragraph.

This change improves the summary so it adds value beyond the stat tiles — concrete, trade-style suggestions plus the supporting analysis/evidence — and renders it with proper markdown structure on the frontend.

## Scope

1. Rewrite the `ExplanationAgent` system prompt to produce a concise, two-section markdown summary.
2. Add markdown rendering to the Summary panel in `OverviewTab.tsx`.

## Section structure

The agent's output is markdown with exactly two `##` headings, in this order:

### `## Suggestion`

A short, trade-style takeaway tied to the regime/direction call and its confidence — e.g. directional bias, and a confidence-appropriate posture (smaller size, tighter stops, wait for confirmation, etc.). Always ends with the fixed disclaimer line:

> *Not financial advice — for informational and research purposes only.*

### `## Analysis & Evidence`

1-3 paragraphs covering:
- What's driving the call (top SHAP features, if present)
- Drift findings and what they mean for confidence in the call
- The data sources and featurizer settings the analysis was built on
- Relevant conversation context from the user-review step, where it adds insight

Same rule as today: only discuss feature-importance/backtest if explicitly present and non-null — never invent or speculate.

Markdown emphasis (`**bold**`, `*italic*`) is used for key terms (regime names, feature names, confidence numbers).

## Backend changes

**`backend/src/agents/explanation_agent.py`**
- Replace `_SYSTEM_PROMPT` with the new two-section instructions described above.
- No change to `make_explanation_agent()` signature.

**`backend/src/services/explanation.py`**
- No changes — `_build_context_block` already supplies regime, direction, drift, feature_importance, backtest, data_manifest, featurizer_config, and recent conversation, which is everything the new prompt needs.

**`backend/src/db/models.py`**
- No changes — `AnalysisResult.summary` remains `str | None`, now containing markdown instead of plain paragraphs.

## Frontend changes

**`frontend/package.json`**
- Add `react-markdown` as a dependency.

**`frontend/components/tabs/OverviewTab.tsx`**
- Replace `<p className="text-sm text-gray-700 whitespace-pre-wrap">{result.summary}</p>` with `<ReactMarkdown>` rendering `result.summary`.
- Provide `components` overrides so headings/paragraphs/emphasis match the existing card style:
  - `h2` → `text-[10px] text-gray-500 font-mono uppercase tracking-widest` (matches other panel headers), with spacing between sections
  - `p` → `text-sm text-gray-700`
  - `strong`/`em` → default (inherit) styling is fine
- The existing "Summary" panel header (`<div>` with "Summary" label) stays as-is, wrapping the rendered markdown.

## Testing

**Backend** (`backend/tests/test_explanation_agent.py`, `test_explanation_service.py`)
- Existing tests mock the LLM response directly, so they aren't coupled to prompt wording and need no changes for correctness.
- Add one new assertion in `test_explanation_agent.py` checking the system prompt contains the two required section headers (`## Suggestion`, `## Analysis & Evidence`) and the disclaimer text, to guard against accidental prompt regressions.

**Frontend** (`frontend/components/tabs/__tests__/OverviewTab.test.tsx`)
- Update the two existing summary tests ("renders the summary panel when summary is present" / "omits the summary panel when summary is null") to use markdown content, e.g. `"## Suggestion\nHold steady.\n\n## Analysis & Evidence\nDriven by rsi_14."`, and assert via `getByRole("heading", { name: /suggestion/i })` and `getByText(/Driven by rsi_14/)`.

## Out of scope

- No changes to `AnalysisResult.summary` field type or DB schema.
- No changes to `_build_context_block` or the explanation service's data flow.
- No new disclaimers/legal review beyond the fixed line specified above.
