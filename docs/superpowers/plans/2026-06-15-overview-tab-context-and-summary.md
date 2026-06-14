# Overview Tab Context & Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a market-context header (market name + description) and an LLM summary panel to the Overview tab, and generalize regime label formatting/coloring so it works for all market profiles (oil, sp500, eurusd), not just oil.

**Architecture:** All changes are frontend-only. `OverviewTab.tsx` gains a `profile?: MarketProfile | null` prop and a `summary` field on its `AnalysisResult` type; two small pure helper functions (`formatRegimeLabel`, `regimeColor`) replace the hardcoded `REGIME_LABELS` dict and inline color ternary. `overview/page.tsx` fetches `/api/profiles`, finds the entry matching the session's `market_profile`, and passes it down.

**Tech Stack:** Next.js 15 (App Router), TypeScript, Tailwind CSS, Vitest + @testing-library/react.

---

### Task 1: Generalize regime label formatting

**Files:**
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Test: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing test**

In `frontend/components/tabs/__tests__/OverviewTab.test.tsx`, add this test inside the existing `describe("OverviewTab", ...)` block (after the last `it(...)`, before the closing `});`):

```tsx
  it("formats non-oil regime labels generically", () => {
    const sp500Result = {
      ...result,
      regime: { ...result.regime, regime: "bull_market", distribution: { bull_market: 10 } },
    };
    render(<OverviewTab result={sp500Result} />);
    expect(screen.getAllByText(/bull market/i).length).toBeGreaterThan(0);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: FAIL — "formats non-oil regime labels generically" fails because `REGIME_LABELS["bull_market"]` is undefined, so the raw `"bull_market"` (underscore, no space) is rendered, which does not match `/bull market/i`.

- [ ] **Step 3: Replace `REGIME_LABELS` with a generic formatter**

In `frontend/components/tabs/OverviewTab.tsx`, replace:

```ts
const REGIME_LABELS: Record<string, string> = {
  range_bound: "Range-Bound",
  bull_supercycle: "Bull Supercycle",
  bust: "Bust",
  geopolitical_spike: "Geopolitical Spike",
};
```

with:

```ts
function formatRegimeLabel(regime: string): string {
  return regime
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
```

- [ ] **Step 4: Update the two usages**

Replace:

```ts
          value={REGIME_LABELS[regime.regime] ?? regime.regime}
```

with:

```ts
          value={formatRegimeLabel(regime.regime)}
```

Replace:

```ts
                label={REGIME_LABELS[r] ?? r}
```

with:

```ts
                label={formatRegimeLabel(r)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: PASS — all tests including "formats non-oil regime labels generically" and the existing "renders regime stat tile with confidence" (which still matches `/range.bound/i` against "Range Bound").

- [ ] **Step 6: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "refactor(frontend): generalize regime label formatting on overview tab"
```

---

### Task 2: Generalize distribution-bar colors by profile regime position

**Files:**
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Test: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing test**

In `frontend/components/tabs/__tests__/OverviewTab.test.tsx`, add a `MarketProfile` fixture and a new test. First, add this import alongside the existing imports at the top of the file:

```tsx
import type { MarketProfile } from "@/lib/api";
```

Then add this fixture after the existing `const result = { ... };` block (top-level, module scope):

```tsx
const sp500Profile: MarketProfile = {
  id: "sp500",
  name: "S&P 500",
  description: "US large-cap equity regime analysis using price, volatility, and macro signals.",
  default_connectors: [],
  default_featurizer_config: {
    windows: [],
    lags: [],
    feature_families: [],
    energy_specific: false,
  },
  regime_labels: ["bull_market", "range_bound", "bear_market", "high_volatility"],
};
```

Then add this test inside the existing `describe("OverviewTab", ...)` block:

```tsx
  it("colors non-oil bearish/bullish regimes based on profile.regime_labels position", () => {
    const sp500Result = {
      ...result,
      regime: {
        ...result.regime,
        regime: "bear_market",
        distribution: { bear_market: 10, bull_market: 5 },
      },
    };
    const { container } = render(<OverviewTab result={sp500Result} profile={sp500Profile} />);
    expect(container.querySelector(".bg-red-600")).toBeTruthy();
    expect(container.querySelector(".bg-emerald-600")).toBeTruthy();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: FAIL — both `r === "bear_market"` and `r === "bull_market"` fall through the existing ternary to the default `"bg-brand"`, so neither `.bg-red-600` nor `.bg-emerald-600` is present in the DOM. Also expect a TypeScript error at this point since `OverviewTab` doesn't accept a `profile` prop yet — that's expected and resolved in the next step.

- [ ] **Step 3: Add `regimeColor` helper and `profile` prop**

In `frontend/components/tabs/OverviewTab.tsx`, add this import at the top of the file (after the existing `import { TabPlaceholder } from "./TabPlaceholder";` line):

```ts
import type { MarketProfile } from "@/lib/api";
```

After the `formatRegimeLabel` function (added in Task 1), add:

```ts
const REGIME_POSITION_COLORS = [
  "bg-emerald-600", // index 0: bullish
  "bg-brand", // index 1: range-bound / neutral
  "bg-red-600", // index 2: bearish
  "bg-amber-500", // index 3: volatility spike
];

function regimeColor(regime: string, profile?: MarketProfile | null): string {
  const idx = profile?.regime_labels.indexOf(regime) ?? -1;
  return REGIME_POSITION_COLORS[idx] ?? "bg-brand";
}
```

Update the `Props` type:

```ts
type Props = { result: AnalysisResult; profile?: MarketProfile | null };
```

Update the component signature:

```ts
export function OverviewTab({ result, profile }: Props) {
```

- [ ] **Step 4: Replace the inline color ternary**

Replace:

```tsx
                color={
                  r === "bull_supercycle"
                    ? "bg-emerald-600"
                    : r === "bust"
                    ? "bg-red-600"
                    : r === "geopolitical_spike"
                    ? "bg-amber-500"
                    : "bg-brand"
                }
```

with:

```tsx
                color={regimeColor(r, profile)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: PASS — `regimeColor("bear_market", sp500Profile)` returns `"bg-red-600"` (index 2) and `regimeColor("bull_market", sp500Profile)` returns `"bg-emerald-600"` (index 0). Existing tests still pass since `regimeColor(r, undefined)` returns `"bg-brand"` for all regimes when no profile is passed (matching the old default branch).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "feat(frontend): color regime distribution bars by profile regime position"
```

---

### Task 3: Add market context header

**Files:**
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Test: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `frontend/components/tabs/__tests__/OverviewTab.test.tsx`, add these tests inside the `describe("OverviewTab", ...)` block:

```tsx
  it("renders market profile name and description when provided", () => {
    render(<OverviewTab result={result} profile={sp500Profile} />);
    expect(screen.getByText("S&P 500")).toBeTruthy();
    expect(screen.getByText(/large-cap equity regime analysis/i)).toBeTruthy();
  });

  it("renders without a profile header when profile is not provided", () => {
    render(<OverviewTab result={result} />);
    expect(screen.queryByText("S&P 500")).toBeNull();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: FAIL — "renders market profile name and description when provided" fails because nothing renders `profile.name`/`profile.description` yet. The second test passes trivially (nothing to find either way) but is included now for completeness.

- [ ] **Step 3: Render the header block**

In `frontend/components/tabs/OverviewTab.tsx`, inside the returned JSX, add the header as the first child of the outer `<div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">`, immediately before the stat-tile grid (`<div className="grid grid-cols-2 sm:grid-cols-4 gap-2">`):

```tsx
      {profile && (
        <div className="flex flex-col gap-0.5">
          <div className="text-sm font-bold text-gray-900">{profile.name}</div>
          <div className="text-xs text-gray-500">{profile.description}</div>
        </div>
      )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: PASS — all tests, including both new ones.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "feat(frontend): show market profile name and description on overview tab"
```

---

### Task 4: Add summary panel

**Files:**
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Test: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `frontend/components/tabs/__tests__/OverviewTab.test.tsx`, add these tests inside the `describe("OverviewTab", ...)` block:

```tsx
  it("renders the summary panel when summary is present", () => {
    render(<OverviewTab result={{ ...result, summary: "Markets are range-bound." }} />);
    expect(screen.getByText("Summary")).toBeTruthy();
    expect(screen.getByText("Markets are range-bound.")).toBeTruthy();
  });

  it("omits the summary panel when summary is null", () => {
    render(<OverviewTab result={{ ...result, summary: null }} />);
    expect(screen.queryByText("Summary")).toBeNull();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: FAIL — "renders the summary panel when summary is present" fails because no "Summary" panel is rendered yet. "omits the summary panel when summary is null" passes trivially.

- [ ] **Step 3: Add `summary` to the `AnalysisResult` type**

In `frontend/components/tabs/OverviewTab.tsx`, update:

```ts
type AnalysisResult = {
  regime?: RegimeResult | null;
  direction?: DirectionResult | null;
  drift?: DriftSummary | null;
  feature_importance?: FeatureImportanceSummary | null;
};
```

to:

```ts
type AnalysisResult = {
  regime?: RegimeResult | null;
  direction?: DirectionResult | null;
  drift?: DriftSummary | null;
  feature_importance?: FeatureImportanceSummary | null;
  summary?: string | null;
};
```

- [ ] **Step 4: Render the summary panel**

In `frontend/components/tabs/OverviewTab.tsx`, add this panel as the last child of the outer `<div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">`, immediately after the closing `</div>` of the `<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">` distribution grid (i.e., as a sibling after that grid, still inside the outer container):

```tsx
      {result.summary && (
        <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
            Summary
          </div>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{result.summary}</p>
        </div>
      )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run components/tabs/__tests__/OverviewTab.test.tsx`
Expected: PASS — all tests, including both new ones.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "feat(frontend): render analysis summary panel on overview tab"
```

---

### Task 5: Wire overview page to fetch and pass the market profile

**Files:**
- Modify: `frontend/app/sessions/[id]/overview/page.tsx`

- [ ] **Step 1: Replace file contents**

Replace the full contents of `frontend/app/sessions/[id]/overview/page.tsx` with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { OverviewTab } from "@/components/tabs/OverviewTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type {
  AnalysisResultDetail,
  DataArtifactDetail,
  MarketProfile,
  PendingSource,
} from "@/lib/api";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources, marketProfile } =
    useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);
  const [profile, setProfile] = useState<MarketProfile | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    const last = artifacts.analysis.at(-1);
    if (!id || !last) return;
    api.getAnalysisArtifact(id, last.artifact_id).then(setLatestAnalysis).catch(() => {});
  }, [id, artifacts.analysis]);

  useEffect(() => {
    if (!marketProfile) return;
    api
      .getProfiles()
      .then((profiles) => setProfile(profiles.find((p) => p.id === marketProfile) ?? null))
      .catch(() => {});
  }, [marketProfile]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <OverviewTab result={latestAnalysis ?? {}} profile={profile} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run type-check`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/sessions/[id]/overview/page.tsx"
git commit -m "feat(frontend): fetch market profile and pass it to overview tab"
```

---

### Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run frontend test suite**

Run: `cd frontend && npm run test`
Expected: all test files pass, including `components/tabs/__tests__/OverviewTab.test.tsx` with all new tests from Tasks 1-4.

- [ ] **Step 2: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: no errors (`eslint . --max-warnings=0`).

- [ ] **Step 3: Run frontend type-check**

Run: `cd frontend && npm run type-check`
Expected: no errors.

- [ ] **Step 4: Manual sanity check of the diff**

Run: `git diff main --stat`
Expected: only these files changed:
- `frontend/components/tabs/OverviewTab.tsx`
- `frontend/components/tabs/__tests__/OverviewTab.test.tsx`
- `frontend/app/sessions/[id]/overview/page.tsx`
- `docs/superpowers/specs/2026-06-15-overview-tab-context-and-summary-design.md`
- `docs/superpowers/plans/2026-06-15-overview-tab-context-and-summary.md`

(plus any files already on `feature/results-dashboard-wiring`, since this branch is based on it).
