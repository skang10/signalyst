# Summary Agent Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the `ExplanationAgent` prompt to produce a concise two-section markdown summary (`## Suggestion` with a disclaimed trade-style takeaway, `## Analysis & Evidence` with supporting reasoning) and render it as markdown in the Overview tab's Summary panel.

**Architecture:** Backend-only prompt change in `backend/src/agents/explanation_agent.py` (the service and data flow are unchanged). Frontend adds `react-markdown` and renders `result.summary` through it in `OverviewTab.tsx`, with `components` overrides so `##` headings and paragraphs match the existing panel styling.

**Tech Stack:** Python (pytest, unittest.mock), TypeScript/React (Vitest, @testing-library/react), `react-markdown`.

---

### Task 1: Rewrite the ExplanationAgent system prompt

**Files:**
- Modify: `backend/src/agents/explanation_agent.py`
- Test: `backend/tests/test_explanation_agent.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_explanation_agent.py` (after the existing `test_make_explanation_agent_has_no_tools` test):

```python
def test_explanation_agent_prompt_specifies_sections_and_disclaimer() -> None:
    agent = make_explanation_agent()
    prompt = agent.system_prompt
    assert "## Suggestion" in prompt
    assert "## Analysis & Evidence" in prompt
    assert "Not financial advice" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_explanation_agent.py::test_explanation_agent_prompt_specifies_sections_and_disclaimer -v`
Expected: FAIL — `assert "## Suggestion" in prompt` fails because the current prompt doesn't contain that string.

- [ ] **Step 3: Replace the system prompt**

In `backend/src/agents/explanation_agent.py`, replace the entire `_SYSTEM_PROMPT` value (lines 5-29) with:

```python
_SYSTEM_PROMPT = """\
You are ExplanationAgent. Write a concise, analyst-style markdown summary of a \
completed market regime analysis for the user to read in the session's activity feed.

The Overview tab already displays the regime call, direction call, confidence levels, \
drift/PSI score, and top feature-importance signal as stat tiles — do not simply restate \
these numbers. Instead, add interpretive value: what the result means, why the model \
reached it, and what to watch out for.

You will be given, in the user message:
- The regime classification result (regime label + confidence)
- The price-direction prediction (direction + confidence)
- Drift-detection findings (whether drift was detected, drifted features, PSI score)
- Feature-importance (SHAP) and backtest results — these may be present or may be null/missing
- The data sources fetched (data manifest) and the featurizer settings used for this run
- Recent conversation turns from the user-review step

Respond with markdown containing exactly two `##` sections, in this order:

## Suggestion
A short, trade-style takeaway tied to the regime/direction call and its confidence — \
e.g. directional bias, and a confidence-appropriate posture (smaller position size, \
tighter stops, wait for confirmation, etc.). Always end this section with the exact line:
*Not financial advice — for informational and research purposes only.*

## Analysis & Evidence
1-3 short paragraphs covering:
- What's driving the call (top SHAP features, if present)
- What the drift findings mean for how much to trust this result
- What data and featurizer settings the analysis was built on
- Relevant conversation context where it adds insight (e.g. if the user changed \
settings or asked about specific tickers/sources during review, connect that to the result)

Use **bold** for key terms (regime names, feature names, confidence numbers).

IMPORTANT: Only discuss feature-importance or backtest results if they are explicitly present \
and non-null in the input. If they are missing, simply omit those references — never invent \
or speculate about SHAP rankings or backtest performance you were not given.

Respond with the markdown summary only — no preamble, no JSON, no extra headers beyond the \
two specified above.
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_explanation_agent.py -v`
Expected: All tests in this file PASS (3 tests: `test_make_explanation_agent_has_no_tools`, `test_explanation_agent_returns_text_and_streams_thought`, `test_explanation_agent_prompt_specifies_sections_and_disclaimer`).

- [ ] **Step 5: Run the explanation service tests to confirm no regressions**

Run: `cd backend && uv run pytest tests/test_explanation_service.py -v`
Expected: All 4 tests PASS (these tests mock the LLM response directly and don't depend on prompt wording).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/explanation_agent.py backend/tests/test_explanation_agent.py
git commit -m "feat(backend): restructure explanation agent summary into Suggestion + Analysis sections"
```

---

### Task 2: Add react-markdown dependency

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install react-markdown**

Run: `cd frontend && npm install react-markdown`

- [ ] **Step 2: Verify it was added**

Run: `cd frontend && grep react-markdown package.json`
Expected: A line like `"react-markdown": "^9.x.x"` (or later) under `dependencies`.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add react-markdown dependency"
```

---

### Task 3: Render the summary as markdown in OverviewTab

**Files:**
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Test: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing test**

In `frontend/components/tabs/__tests__/OverviewTab.test.tsx`, replace the existing `"renders the summary panel when summary is present"` test (the one that checks `summary: "Markets are range-bound."`) with:

```tsx
  it("renders the summary panel with markdown sections when summary is present", () => {
    render(
      <OverviewTab
        result={{
          ...result,
          summary:
            "## Suggestion\nHold steady.\n\n## Analysis & Evidence\nDriven by **rsi_14**.",
        }}
      />,
    );
    expect(screen.getByText("Summary")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Suggestion" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Analysis & Evidence" })).toBeTruthy();
    expect(screen.getByText("Hold steady.")).toBeTruthy();
    expect(screen.getByText("rsi_14")).toBeTruthy();
  });
```

Leave the `"omits the summary panel when summary is null"` test unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: FAIL — the new test fails because `result.summary` is currently rendered as a single `<p>` with `whitespace-pre-wrap`, so `screen.getByRole("heading", { name: "Suggestion" })` finds nothing (the literal text `## Suggestion` is rendered, not a heading).

(Always `cd frontend` first — running vitest from the repo root causes jsdom to not load and produces unrelated "document is not defined" errors.)

- [ ] **Step 3: Implement markdown rendering**

In `frontend/components/tabs/OverviewTab.tsx`:

Add the import at the top of the file (after the existing imports):

```tsx
import ReactMarkdown from "react-markdown";
```

Replace the summary panel block (the `{result.summary && (...)}` block near the end of the component) with:

```tsx
      {result.summary && (
        <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
            Summary
          </div>
          <ReactMarkdown
            components={{
              h2: ({ children }) => (
                <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
                  {children}
                </div>
              ),
              p: ({ children }) => <p className="text-sm text-gray-700">{children}</p>,
            }}
          >
            {result.summary}
          </ReactMarkdown>
        </div>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: All 11 tests in this file PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "feat(frontend): render summary as markdown with Suggestion/Analysis sections"
```

---

### Task 4: Full verification

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: All tests PASS.

- [ ] **Step 2: Run backend lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: No errors.

- [ ] **Step 3: Run full frontend test suite**

Run: `cd frontend && npm run test`
Expected: All tests PASS, including 11 tests in `OverviewTab.test.tsx`.

- [ ] **Step 4: Run frontend lint and type-check**

Run: `cd frontend && npm run lint && npm run type-check`
Expected: No errors.

- [ ] **Step 5: Manually verify in the browser (optional but recommended)**

Run `make dev-backend` and `make dev-frontend`, open a session with a completed analysis on the Overview tab, and confirm the Summary panel shows a "Suggestion" heading followed by "Analysis & Evidence" heading, each styled like the other panel labels (small uppercase mono gray text), with body paragraphs in normal text and `**bold**` terms rendered bold.

---

### Task 5: Finish the branch

- [ ] Use superpowers:finishing-a-development-branch to verify tests, present options (merge/PR/keep/discard), and complete the work.
