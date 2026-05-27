# Rich Results Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current single-column results panel with a 5-tab quant-terminal dashboard (Overview, Features, Drift, Backtest, Summary) with a persistent icon sidebar, placeholder states for absent backend data, and full unit test coverage.

**Architecture:** `ResultsTabs` owns active-tab state and renders an icon sidebar in sync with a tab bar; each tab is a focused component receiving typed props from `AnalysisResult`; `ResultsPanel` delegates all rendering to `ResultsTabs` and keeps its own skeleton/error/idle guards. All data comes from the existing `GET /api/runs/{run_id}` response — no new backend endpoints.

**Tech Stack:** Next.js 15 App Router, TypeScript, Tailwind CSS v4, Recharts (BarChart), Vitest + @testing-library/react, jsdom

---

## File Map

**New files:**
- `frontend/components/tabs/TabPlaceholder.tsx`
- `frontend/components/tabs/OverviewTab.tsx`
- `frontend/components/tabs/FeaturesTab.tsx`
- `frontend/components/tabs/DriftTab.tsx`
- `frontend/components/tabs/BacktestTab.tsx`
- `frontend/components/tabs/SummaryTab.tsx`
- `frontend/components/ResultsTabs.tsx`
- `frontend/components/tabs/__tests__/TabPlaceholder.test.tsx`
- `frontend/components/tabs/__tests__/OverviewTab.test.tsx`
- `frontend/components/tabs/__tests__/FeaturesTab.test.tsx`
- `frontend/components/tabs/__tests__/DriftTab.test.tsx`
- `frontend/components/tabs/__tests__/BacktestTab.test.tsx`
- `frontend/components/tabs/__tests__/SummaryTab.test.tsx`
- `frontend/components/__tests__/ResultsTabs.test.tsx`

**Modified files:**
- `frontend/lib/api.ts` — add `DriftResult`, `FeatureImportanceResult`, `BacktestResult`; update `AnalysisResult` fields from `unknown` to typed
- `frontend/vitest.setup.ts` — add `ResizeObserver` mock (required by Recharts in jsdom)
- `frontend/components/ResultsPanel.tsx` — replace card stack with `<ResultsTabs result={result} />`
- `frontend/components/__tests__/ResultsPanel.test.tsx` — update assertions

**Deleted files (after Task 9 passes):**
- `frontend/components/RegimeCard.tsx`
- `frontend/components/DirectionCard.tsx`
- `frontend/components/SummaryPanel.tsx`
- `frontend/components/__tests__/RegimeCard.test.tsx`
- `frontend/components/__tests__/DirectionCard.test.tsx`

---

### Task 1: Type API fields + add ResizeObserver mock

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/vitest.setup.ts`

- [ ] **Step 1: Write the failing type test**

Create `frontend/lib/__tests__/api-types.test.ts`:

```typescript
import { describe, it, expectTypeOf } from "vitest";
import type { AnalysisResult, DriftResult, FeatureImportanceResult, BacktestResult } from "../api";

describe("AnalysisResult types", () => {
  it("drift is DriftResult | null", () => {
    expectTypeOf<AnalysisResult["drift"]>().toEqualTypeOf<DriftResult | null>();
  });
  it("feature_importance is FeatureImportanceResult | null", () => {
    expectTypeOf<AnalysisResult["feature_importance"]>().toEqualTypeOf<FeatureImportanceResult | null>();
  });
  it("backtest is BacktestResult | null", () => {
    expectTypeOf<AnalysisResult["backtest"]>().toEqualTypeOf<BacktestResult | null>();
  });
});
```

- [ ] **Step 2: Run to confirm type errors**

```bash
cd frontend && npm run type-check 2>&1 | head -30
```

Expected: errors mentioning `DriftResult`, `FeatureImportanceResult`, `BacktestResult` not found.

- [ ] **Step 3: Add types to `frontend/lib/api.ts`**

Find the existing `AnalysisResult` type and the lines with `drift: unknown`, `feature_importance: unknown`, `backtest: unknown`. Add these three new types directly above `AnalysisResult`, then update the three fields:

```typescript
export type DriftResult = {
  drift_detected: boolean;
  psi_score: number;
  drifted_features: string[];
  ks_results: Record<string, { statistic: number; p_value: number }>;
};

export type FeatureImportanceResult = {
  top_features: Array<{ name: string; importance: number }>;
  n_features_evaluated: number;
  n_samples_explained: number;
};

export type BacktestResult = {
  regime_accuracy: number;
  strategy_sharpe: number;
  benchmark_sharpe: number;
  n_windows: number;
};
```

Then change the three `AnalysisResult` fields:

```typescript
// Before:
drift: unknown;
feature_importance: unknown;
backtest: unknown;

// After:
drift: DriftResult | null;
feature_importance: FeatureImportanceResult | null;
backtest: BacktestResult | null;
```

- [ ] **Step 4: Add ResizeObserver mock to `frontend/vitest.setup.ts`**

Recharts uses `ResizeObserver` internally; jsdom doesn't implement it, causing tests to throw. Add this at the bottom of the file:

```typescript
import '@testing-library/jest-dom';

globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
```

- [ ] **Step 5: Run type check and tests**

```bash
cd frontend && npm run type-check && npm run test -- --run 2>&1 | tail -20
```

Expected: type check passes, existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/vitest.setup.ts frontend/lib/__tests__/api-types.test.ts
git commit -m "feat: type drift/features/backtest fields in AnalysisResult; add ResizeObserver mock"
```

---

### Task 2: TabPlaceholder component

**Files:**
- Create: `frontend/components/tabs/TabPlaceholder.tsx`
- Create: `frontend/components/tabs/__tests__/TabPlaceholder.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/tabs/__tests__/TabPlaceholder.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TabPlaceholder } from "../TabPlaceholder";

describe("TabPlaceholder", () => {
  it("renders the icon, title, and reason", () => {
    render(
      <TabPlaceholder
        icon="≡"
        title="Feature importance not available"
        reason="Not computed in this run."
      />
    );
    expect(screen.getByText("≡")).toBeTruthy();
    expect(screen.getByText("Feature importance not available")).toBeTruthy();
    expect(screen.getByText("Not computed in this run.")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/TabPlaceholder 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `TabPlaceholder`**

Create `frontend/components/tabs/TabPlaceholder.tsx`:

```tsx
type TabPlaceholderProps = {
  icon: string;
  title: string;
  reason: string;
};

export function TabPlaceholder({ icon, title, reason }: TabPlaceholderProps) {
  return (
    <div className="flex items-center justify-center h-full min-h-[180px]">
      <div className="text-center max-w-[280px]">
        <div className="text-[28px] text-slate-800 mb-3">{icon}</div>
        <div className="text-xs text-slate-400 font-mono font-semibold mb-1.5">
          {title}
        </div>
        <div className="text-[10px] text-slate-600 font-mono leading-relaxed">
          {reason}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/TabPlaceholder 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/TabPlaceholder.tsx frontend/components/tabs/__tests__/TabPlaceholder.test.tsx
git commit -m "feat: add TabPlaceholder component"
```

---

### Task 3: OverviewTab component

**Files:**
- Create: `frontend/components/tabs/OverviewTab.tsx`
- Create: `frontend/components/tabs/__tests__/OverviewTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/tabs/__tests__/OverviewTab.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OverviewTab } from "../OverviewTab";
import type { AnalysisResult } from "../../../lib/api";

const result: AnalysisResult = {
  regime: {
    regime: "range_bound",
    confidence: 0.9503,
    entropy: 0.187,
    distribution: { range_bound: 24, bull_supercycle: 4, bust: 2 },
  },
  direction: {
    direction: "down",
    confidence: 0.7046,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20, up: 10 },
  },
  drift: {
    drift_detected: true,
    psi_score: 0.32,
    drifted_features: ["rsi_14"],
    ks_results: { rsi_14: { statistic: 0.41, p_value: 0.001 } },
  },
  feature_importance: {
    top_features: [{ name: "rsi_14", importance: 0.42 }],
    n_features_evaluated: 20,
    n_samples_explained: 100,
  },
  backtest: null,
  summary: "Range-bound regime.",
  usage: { input_tokens: 1000, output_tokens: 100, estimated_cost_usd: 0.01 },
  data_manifest: {},
};

describe("OverviewTab", () => {
  it("renders regime stat tile with confidence", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText(/range.bound/i)).toBeTruthy();
    expect(screen.getByText(/95\.0%/)).toBeTruthy();
  });

  it("renders direction stat tile", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText(/down/i)).toBeTruthy();
    expect(screen.getByText(/70\.5%/)).toBeTruthy();
  });

  it("renders drift stat tile with PSI score", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText(/0\.32/)).toBeTruthy();
  });

  it("renders top signal stat tile", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText(/rsi_14/i)).toBeTruthy();
    expect(screen.getByText(/0\.42/)).toBeTruthy();
  });

  it("renders placeholder when regime is null", () => {
    render(<OverviewTab result={{ ...result, regime: null as any, direction: null as any }} />);
    expect(screen.getByText(/analysis incomplete/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/OverviewTab 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `OverviewTab`**

Create `frontend/components/tabs/OverviewTab.tsx`:

```tsx
import type { AnalysisResult } from "../../lib/api";
import { TabPlaceholder } from "./TabPlaceholder";

const REGIME_LABELS: Record<string, string> = {
  range_bound: "Range-Bound",
  bull_supercycle: "Bull Supercycle",
  bust: "Bust",
  geopolitical_spike: "Geopolitical Spike",
};

function StatTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-slate-600 font-mono">{sub}</div>}
    </div>
  );
}

function DistBar({
  label,
  pct,
  color,
}: {
  label: string;
  pct: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <div className="w-28 text-right text-slate-400 truncate">{label}</div>
      <div className="flex-1 bg-slate-900 rounded h-2 overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-8 text-slate-500 text-right">{pct.toFixed(0)}%</div>
    </div>
  );
}

type Props = { result: AnalysisResult };

export function OverviewTab({ result }: Props) {
  const { regime, direction, drift, feature_importance } = result;

  if (!regime || !direction) {
    return (
      <TabPlaceholder
        icon="▦"
        title="Analysis incomplete"
        reason="Regime or direction result missing — the run may have failed mid-way."
      />
    );
  }

  const regimeTotal = Object.values(regime.distribution).reduce((s, v) => s + v, 0);
  const directionTotal = Object.values(direction.distribution).reduce((s, v) => s + v, 0);

  const psiSeverity =
    drift == null
      ? "No data"
      : drift.psi_score < 0.1
      ? "Stable"
      : drift.psi_score < 0.2
      ? "Moderate"
      : "High";

  const topSignalName = feature_importance?.top_features[0]?.name ?? "—";
  const topSignalScore = feature_importance?.top_features[0]?.importance;

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      {/* Stat tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatTile
          label="Regime"
          value={REGIME_LABELS[regime.regime] ?? regime.regime}
          sub={`${(regime.confidence * 100).toFixed(1)}% confidence`}
          accent="text-violet-400"
        />
        <StatTile
          label="WTI Direction"
          value={direction.direction === "up" ? "▲ Up" : "▼ Down"}
          sub={`${(direction.confidence * 100).toFixed(1)}% confidence`}
          accent={direction.direction === "up" ? "text-emerald-400" : "text-red-400"}
        />
        <StatTile
          label="Drift"
          value={drift ? drift.psi_score.toFixed(2) : "—"}
          sub={psiSeverity}
          accent={drift?.drift_detected ? "text-amber-400" : "text-slate-400"}
        />
        <StatTile
          label="Top Signal"
          value={topSignalName}
          sub={topSignalScore != null ? `SHAP ${topSignalScore.toFixed(2)}` : undefined}
          accent="text-violet-300"
        />
      </div>

      {/* Distribution cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Regime distribution */}
        <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-1">
            Regime Distribution
          </div>
          {Object.entries(regime.distribution)
            .sort((a, b) => b[1] - a[1])
            .map(([r, count]) => (
              <DistBar
                key={r}
                label={REGIME_LABELS[r] ?? r}
                pct={regimeTotal > 0 ? (count / regimeTotal) * 100 : 0}
                color={
                  r === "bull_supercycle"
                    ? "bg-emerald-600"
                    : r === "bust"
                    ? "bg-red-600"
                    : r === "geopolitical_spike"
                    ? "bg-amber-500"
                    : "bg-violet-600"
                }
              />
            ))}
        </div>

        {/* Direction distribution */}
        <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-1">
            Direction Distribution
          </div>
          {Object.entries(direction.distribution)
            .sort((a, b) => b[1] - a[1])
            .map(([d, count]) => (
              <DistBar
                key={d}
                label={d === "up" ? "▲ Up" : "▼ Down"}
                pct={directionTotal > 0 ? (count / directionTotal) * 100 : 0}
                color={d === "up" ? "bg-emerald-600" : "bg-red-600"}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/OverviewTab 2>&1 | tail -15
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/OverviewTab.tsx frontend/components/tabs/__tests__/OverviewTab.test.tsx
git commit -m "feat: add OverviewTab with stat tiles and distribution bars"
```

---

### Task 4: FeaturesTab component

**Files:**
- Create: `frontend/components/tabs/FeaturesTab.tsx`
- Create: `frontend/components/tabs/__tests__/FeaturesTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/tabs/__tests__/FeaturesTab.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FeaturesTab } from "../FeaturesTab";
import type { FeatureImportanceResult } from "../../../lib/api";

const features: FeatureImportanceResult = {
  top_features: [
    { name: "rsi_14", importance: 0.42 },
    { name: "macd_signal", importance: 0.27 },
    { name: "eia_storage", importance: 0.15 },
  ],
  n_features_evaluated: 20,
  n_samples_explained: 100,
};

describe("FeaturesTab", () => {
  it("renders feature names and importance values", () => {
    render(<FeaturesTab features={features} />);
    expect(screen.getByText("rsi_14")).toBeTruthy();
    expect(screen.getByText("0.420")).toBeTruthy();
    expect(screen.getByText("macd_signal")).toBeTruthy();
    expect(screen.getByText("eia_storage")).toBeTruthy();
  });

  it("renders footer with feature count and sample count", () => {
    render(<FeaturesTab features={features} />);
    expect(screen.getByText(/20 features/)).toBeTruthy();
    expect(screen.getByText(/100 samples/)).toBeTruthy();
  });

  it("renders placeholder when features is null", () => {
    render(<FeaturesTab features={null} />);
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/FeaturesTab 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `FeaturesTab`**

Create `frontend/components/tabs/FeaturesTab.tsx`:

```tsx
import type { FeatureImportanceResult } from "../../lib/api";
import { TabPlaceholder } from "./TabPlaceholder";

type Props = { features: FeatureImportanceResult | null };

export function FeaturesTab({ features }: Props) {
  if (!features) {
    return (
      <TabPlaceholder
        icon="≡"
        title="Feature importance not available"
        reason="Not computed in this run. Enable in Full mode or add evaluate_features to tasks."
      />
    );
  }

  const max = features.top_features[0]?.importance ?? 1;

  return (
    <div className="p-4 flex flex-col h-full">
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-4 flex flex-col gap-2 flex-1">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">
          SHAP Feature Importance
        </div>
        <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
          {features.top_features.map((f, i) => (
            <div key={f.name} className="flex items-center gap-2">
              <div className="w-32 text-right text-xs text-slate-400 font-mono truncate">
                {f.name}
              </div>
              <div className="flex-1 bg-slate-900 rounded h-3 overflow-hidden">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(f.importance / max) * 100}%`,
                    background: `linear-gradient(to right, #7c3aed, #4f46e5)`,
                    opacity: 1 - i * 0.06,
                  }}
                />
              </div>
              <div className="w-12 text-right text-xs text-slate-400 font-mono">
                {f.importance.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-slate-600 font-mono pt-2 border-t border-slate-800">
          {features.n_features_evaluated} features · {features.n_samples_explained} samples · SHAP
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/FeaturesTab 2>&1 | tail -10
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/FeaturesTab.tsx frontend/components/tabs/__tests__/FeaturesTab.test.tsx
git commit -m "feat: add FeaturesTab with SHAP bar chart"
```

---

### Task 5: DriftTab component

**Files:**
- Create: `frontend/components/tabs/DriftTab.tsx`
- Create: `frontend/components/tabs/__tests__/DriftTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/tabs/__tests__/DriftTab.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DriftTab } from "../DriftTab";
import type { DriftResult } from "../../../lib/api";

const drift: DriftResult = {
  drift_detected: true,
  psi_score: 0.32,
  drifted_features: ["rsi_14", "macd_signal"],
  ks_results: {
    rsi_14: { statistic: 0.41, p_value: 0.001 },
    macd_signal: { statistic: 0.29, p_value: 0.018 },
    eia_storage: { statistic: 0.08, p_value: 0.42 },
  },
};

describe("DriftTab", () => {
  it("renders PSI score tile", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("0.32")).toBeTruthy();
  });

  it("renders count of drifted features", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("shows DRIFT badge for drifted features", () => {
    render(<DriftTab drift={drift} />);
    const badges = screen.getAllByText("DRIFT");
    expect(badges.length).toBe(2);
  });

  it("shows OK badge for non-drifted features", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("OK")).toBeTruthy();
  });

  it("renders placeholder when drift is null", () => {
    render(<DriftTab drift={null} />);
    expect(screen.getByText(/drift analysis not available/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/DriftTab 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `DriftTab`**

Create `frontend/components/tabs/DriftTab.tsx`:

```tsx
import type { DriftResult } from "../../lib/api";
import { TabPlaceholder } from "./TabPlaceholder";

type Props = { drift: DriftResult | null };

function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}

const PSI_INTERPRETATION: (psi: number, detected: boolean) => string = (psi, detected) => {
  if (!detected) return "Feature distributions are stable. The regime model is operating within its training distribution.";
  if (psi < 0.2) return "Moderate distributional shift detected. Monitor carefully — forecasts may be slightly less reliable than during model training.";
  return "Significant distributional shift detected. The current market regime may be outside the model's training distribution. Treat directional forecasts with higher uncertainty.";
};

export function DriftTab({ drift }: Props) {
  if (!drift) {
    return (
      <TabPlaceholder
        icon="⊘"
        title="Drift analysis not available"
        reason="Not computed in this run. Enable in Full mode or add detect_drift to tasks."
      />
    );
  }

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      {/* Stat tiles */}
      <div className="grid grid-cols-3 gap-2">
        <StatTile
          label="PSI Score"
          value={drift.psi_score.toFixed(2)}
          accent={drift.drift_detected ? "text-amber-400" : "text-slate-300"}
        />
        <StatTile
          label="Drifted Features"
          value={String(drift.drifted_features.length)}
          accent={drift.drifted_features.length > 0 ? "text-amber-400" : "text-slate-300"}
        />
        <StatTile
          label="Drift Detected"
          value={drift.drift_detected ? "YES" : "NO"}
          accent={drift.drift_detected ? "text-amber-400" : "text-emerald-400"}
        />
      </div>

      {/* Feature table */}
      <div className="bg-[#0d0d18] border border-slate-800 rounded overflow-hidden">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest p-3 border-b border-slate-800">
          Feature KS Statistics
        </div>
        <div className="divide-y divide-slate-800">
          {Object.entries(drift.ks_results)
            .sort((a, b) => b[1].statistic - a[1].statistic)
            .map(([feature, { statistic, p_value }]) => {
              const isDrifted = drift.drifted_features.includes(feature);
              return (
                <div
                  key={feature}
                  className="flex items-center gap-3 px-3 py-2 text-xs font-mono"
                >
                  <div className="flex-1 text-slate-300 truncate">{feature}</div>
                  <div className="text-slate-500 w-12 text-right">
                    {statistic.toFixed(3)}
                  </div>
                  <div className="text-slate-600 w-12 text-right">
                    p={p_value.toFixed(3)}
                  </div>
                  <div
                    className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                      isDrifted
                        ? "bg-amber-950 text-amber-400"
                        : "bg-slate-800 text-slate-500"
                    }`}
                  >
                    {isDrifted ? "DRIFT" : "OK"}
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* Interpretation */}
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-3">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">
          Interpretation
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          {PSI_INTERPRETATION(drift.psi_score, drift.drift_detected)}
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/DriftTab 2>&1 | tail -10
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/DriftTab.tsx frontend/components/tabs/__tests__/DriftTab.test.tsx
git commit -m "feat: add DriftTab with PSI tiles, feature table, and interpretation"
```

---

### Task 6: BacktestTab component

**Files:**
- Create: `frontend/components/tabs/BacktestTab.tsx`
- Create: `frontend/components/tabs/__tests__/BacktestTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Note: Recharts `BarChart` renders to SVG in jsdom but sizes at 0; we mock `recharts` to avoid `ResizeObserver` noise in output.

Create `frontend/components/tabs/__tests__/BacktestTab.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { BacktestTab } from "../BacktestTab";
import type { BacktestResult } from "../../../lib/api";

const backtest: BacktestResult = {
  regime_accuracy: 0.74,
  strategy_sharpe: 1.42,
  benchmark_sharpe: 0.87,
  n_windows: 12,
};

describe("BacktestTab", () => {
  it("renders regime accuracy as percentage", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText(/74\.0%/)).toBeTruthy();
  });

  it("renders strategy Sharpe", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText("1.42")).toBeTruthy();
  });

  it("renders benchmark Sharpe", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText("0.87")).toBeTruthy();
  });

  it("renders the bar chart", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByTestId("bar-chart")).toBeTruthy();
  });

  it("renders n_windows", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText(/12 windows/)).toBeTruthy();
  });

  it("renders placeholder when backtest is null", () => {
    render(<BacktestTab backtest={null} />);
    expect(screen.getByText(/backtest not available/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/BacktestTab 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `BacktestTab`**

Create `frontend/components/tabs/BacktestTab.tsx`:

```tsx
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { BacktestResult } from "../../lib/api";
import { TabPlaceholder } from "./TabPlaceholder";

type Props = { backtest: BacktestResult | null };

function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-2xl font-mono font-bold ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}

export function BacktestTab({ backtest }: Props) {
  if (!backtest) {
    return (
      <TabPlaceholder
        icon="↗"
        title="Backtest not available"
        reason="Not run in quick mode. Switch to Full mode to enable walk-forward evaluation."
      />
    );
  }

  const chartData = [
    {
      name: "Sharpe Ratio",
      Strategy: +backtest.strategy_sharpe.toFixed(2),
      Benchmark: +backtest.benchmark_sharpe.toFixed(2),
    },
  ];

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      {/* Metric tiles */}
      <div className="grid grid-cols-3 gap-2">
        <MetricTile
          label="Regime Accuracy"
          value={`${(backtest.regime_accuracy * 100).toFixed(1)}%`}
          accent="text-violet-400"
        />
        <MetricTile
          label="Strategy Sharpe"
          value={backtest.strategy_sharpe.toFixed(2)}
          accent={backtest.strategy_sharpe > backtest.benchmark_sharpe ? "text-emerald-400" : "text-slate-300"}
        />
        <MetricTile
          label="Benchmark Sharpe"
          value={backtest.benchmark_sharpe.toFixed(2)}
          accent="text-slate-400"
        />
      </div>

      {/* Bar chart */}
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-4 flex-1 min-h-[180px]">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-3">
          Strategy vs Benchmark Sharpe
        </div>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={chartData} barCategoryGap="40%">
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#475569", fontFamily: "monospace" }} />
            <YAxis tick={{ fontSize: 10, fill: "#475569", fontFamily: "monospace" }} />
            <Tooltip
              contentStyle={{
                background: "#0d0d18",
                border: "1px solid #1e293b",
                borderRadius: 4,
                fontSize: 11,
                fontFamily: "monospace",
              }}
            />
            <Legend wrapperStyle={{ fontSize: 10, fontFamily: "monospace" }} />
            <Bar dataKey="Strategy" fill="#7c3aed" radius={[2, 2, 0, 0]} />
            <Bar dataKey="Benchmark" fill="#475569" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="text-[10px] text-slate-600 font-mono mt-2">
          {backtest.n_windows} windows · walk-forward evaluation
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/BacktestTab 2>&1 | tail -10
```

Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/BacktestTab.tsx frontend/components/tabs/__tests__/BacktestTab.test.tsx
git commit -m "feat: add BacktestTab with metric tiles and Sharpe bar chart"
```

---

### Task 7: SummaryTab component

**Files:**
- Create: `frontend/components/tabs/SummaryTab.tsx`
- Create: `frontend/components/tabs/__tests__/SummaryTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/tabs/__tests__/SummaryTab.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SummaryTab } from "../SummaryTab";

describe("SummaryTab", () => {
  it("renders the summary text", () => {
    render(<SummaryTab summary="Range-bound regime with high confidence. **Strong** signals." />);
    expect(screen.getByText(/range-bound regime/i)).toBeTruthy();
  });

  it("renders bold text from **markdown**", () => {
    render(<SummaryTab summary="This is **important**." />);
    const strong = document.querySelector("strong");
    expect(strong?.textContent).toBe("important");
  });

  it("renders placeholder when summary is empty", () => {
    render(<SummaryTab summary="" />);
    expect(screen.getByText(/no summary available/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/SummaryTab 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `SummaryTab`**

Create `frontend/components/tabs/SummaryTab.tsx`:

```tsx
import { TabPlaceholder } from "./TabPlaceholder";

type Props = { summary: string };

function renderSummary(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function SummaryTab({ summary }: Props) {
  if (!summary) {
    return (
      <TabPlaceholder
        icon="✎"
        title="No summary available"
        reason="The agent did not produce a written summary for this run."
      />
    );
  }

  return (
    <div className="p-4 h-full overflow-y-auto">
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-5">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-4">
          Agent Narrative
        </div>
        <p
          className="text-sm text-slate-300 leading-7"
          dangerouslySetInnerHTML={{ __html: renderSummary(summary) }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/tabs/__tests__/SummaryTab 2>&1 | tail -10
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/tabs/SummaryTab.tsx frontend/components/tabs/__tests__/SummaryTab.test.tsx
git commit -m "feat: add SummaryTab with bold markdown rendering"
```

---

### Task 8: ResultsTabs component

**Files:**
- Create: `frontend/components/ResultsTabs.tsx`
- Create: `frontend/components/__tests__/ResultsTabs.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/__tests__/ResultsTabs.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { ResultsTabs } from "../ResultsTabs";
import type { AnalysisResult } from "../../lib/api";

const result: AnalysisResult = {
  regime: {
    regime: "range_bound",
    confidence: 0.95,
    entropy: 0.187,
    distribution: { range_bound: 24 },
  },
  direction: {
    direction: "down",
    confidence: 0.70,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20 },
  },
  drift: null,
  feature_importance: null,
  backtest: null,
  summary: "Test summary.",
  usage: { input_tokens: 100, output_tokens: 10, estimated_cost_usd: 0.001 },
  data_manifest: {},
};

describe("ResultsTabs", () => {
  it("defaults to Overview tab", () => {
    render(<ResultsTabs result={result} />);
    expect(screen.getByText(/range.bound/i)).toBeTruthy();
  });

  it("switches to Summary tab when clicked", async () => {
    render(<ResultsTabs result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /summary/i }));
    expect(screen.getByText("Test summary.")).toBeTruthy();
  });

  it("shows Features placeholder when clicked (null data)", async () => {
    render(<ResultsTabs result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /features/i }));
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });

  it("shows Drift placeholder when clicked (null data)", async () => {
    render(<ResultsTabs result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /drift/i }));
    expect(screen.getByText(/drift analysis not available/i)).toBeTruthy();
  });

  it("shows Backtest placeholder when clicked (null data)", async () => {
    render(<ResultsTabs result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /backtest/i }));
    expect(screen.getByText(/backtest not available/i)).toBeTruthy();
  });

  it("sidebar icon click also switches tab", async () => {
    render(<ResultsTabs result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /summary sidebar/i }));
    expect(screen.getByText("Test summary.")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm run test -- --run components/__tests__/ResultsTabs 2>&1 | tail -15
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `ResultsTabs`**

Create `frontend/components/ResultsTabs.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { AnalysisResult } from "../lib/api";
import { OverviewTab } from "./tabs/OverviewTab";
import { FeaturesTab } from "./tabs/FeaturesTab";
import { DriftTab } from "./tabs/DriftTab";
import { BacktestTab } from "./tabs/BacktestTab";
import { SummaryTab } from "./tabs/SummaryTab";

type TabId = "overview" | "features" | "drift" | "backtest" | "summary";

const TABS: Array<{ id: TabId; label: string; icon: string }> = [
  { id: "overview", label: "Overview", icon: "▦" },
  { id: "features", label: "Features", icon: "≡" },
  { id: "drift", label: "Drift", icon: "⊘" },
  { id: "backtest", label: "Backtest", icon: "↗" },
  { id: "summary", label: "Summary", icon: "✎" },
];

type Props = { result: AnalysisResult };

export function ResultsTabs({ result }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  function renderTab() {
    switch (activeTab) {
      case "overview":
        return <OverviewTab result={result} />;
      case "features":
        return <FeaturesTab features={result.feature_importance} />;
      case "drift":
        return <DriftTab drift={result.drift} />;
      case "backtest":
        return <BacktestTab backtest={result.backtest} />;
      case "summary":
        return <SummaryTab summary={result.summary} />;
    }
  }

  return (
    <div className="flex h-full">
      {/* Icon sidebar */}
      <div className="w-10 flex flex-col items-center py-3 gap-1 border-r border-slate-800 bg-[#07070f] shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            aria-label={`${tab.label} sidebar`}
            title={tab.label}
            onClick={() => setActiveTab(tab.id)}
            className={`w-8 h-8 flex items-center justify-center rounded text-sm transition-colors ${
              activeTab === tab.id
                ? "bg-violet-950 text-violet-400"
                : "text-slate-600 hover:text-slate-400 hover:bg-slate-800"
            }`}
          >
            {tab.icon}
          </button>
        ))}
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Tab bar */}
        <div className="flex border-b border-slate-800 bg-[#07070f] shrink-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              aria-label={tab.label}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 text-xs font-mono transition-colors border-b-2 ${
                activeTab === tab.id
                  ? "border-violet-500 text-violet-400"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden bg-[#07070f]">{renderTab()}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run components/__tests__/ResultsTabs 2>&1 | tail -15
```

Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ResultsTabs.tsx frontend/components/__tests__/ResultsTabs.test.tsx
git commit -m "feat: add ResultsTabs with icon sidebar and 5-tab navigation"
```

---

### Task 9: Wire up ResultsPanel, delete old cards, final test run

**Files:**
- Modify: `frontend/components/ResultsPanel.tsx`
- Modify: `frontend/components/__tests__/ResultsPanel.test.tsx`
- Delete: `frontend/components/RegimeCard.tsx`
- Delete: `frontend/components/DirectionCard.tsx`
- Delete: `frontend/components/SummaryPanel.tsx`
- Delete: `frontend/components/__tests__/RegimeCard.test.tsx`
- Delete: `frontend/components/__tests__/DirectionCard.test.tsx`

- [ ] **Step 1: Update `ResultsPanel.tsx`**

Read the current file first to get exact content, then replace the card stack render with `<ResultsTabs>`. The skeleton, error, and idle guard states are kept unchanged. The new `ResultsPanel.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { fetchRun } from "../lib/api";
import type { AnalysisResult } from "../lib/api";
import { ResultsTabs } from "./ResultsTabs";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "done"; result: AnalysisResult };

export default function ResultsPanel({ runId }: { runId: string | null }) {
  const [state, setState] = useState<State>({ status: "idle" });

  useEffect(() => {
    if (!runId) {
      setState({ status: "idle" });
      return;
    }
    setState({ status: "loading" });
    fetchRun(runId)
      .then((result) => setState({ status: "done", result }))
      .catch((err) => setState({ status: "error", message: String(err) }));
  }, [runId]);

  if (state.status === "idle") {
    return (
      <div className="flex items-center justify-center h-full text-slate-600 text-xs font-mono">
        No analysis yet
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <div className="flex items-center justify-center h-full text-slate-600 text-xs font-mono animate-pulse">
        Loading results…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex items-center justify-center h-full text-red-400 text-xs font-mono">
        {state.message}
      </div>
    );
  }

  return <ResultsTabs result={state.result} />;
}
```

> **Note:** Check the actual current `ResultsPanel.tsx` before editing — the props signature (especially how `runId` is passed in) must match how `app/page.tsx` calls it. If `ResultsPanel` currently takes no props or different props, adjust accordingly. Do not change `app/page.tsx`.

- [ ] **Step 2: Update `ResultsPanel.test.tsx`**

Replace the current test content with assertions that check the new tab-based output:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ResultsPanel from "../ResultsPanel";
import type { AnalysisResult } from "../../lib/api";

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockResult: AnalysisResult = {
  regime: {
    regime: "range_bound",
    confidence: 0.9503,
    entropy: 0.187,
    distribution: { range_bound: 24 },
  },
  direction: {
    direction: "down",
    confidence: 0.7046,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20 },
  },
  drift: null,
  feature_importance: null,
  backtest: null,
  summary: "Range-bound regime with high confidence.",
  usage: { input_tokens: 1000, output_tokens: 100, estimated_cost_usd: 0.01 },
  data_manifest: {},
};

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    fetchRun: vi.fn().mockResolvedValue(mockResult),
  };
});

describe("ResultsPanel", () => {
  it("shows idle state when no runId", () => {
    render(<ResultsPanel runId={null} />);
    expect(screen.getByText(/no analysis yet/i)).toBeTruthy();
  });

  it("shows loading then renders tabs", async () => {
    render(<ResultsPanel runId="run-123" />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/range.bound/i)).toBeTruthy());
  });

  it("shows error state on fetch failure", async () => {
    const { fetchRun } = await import("../../lib/api");
    (fetchRun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Network error"));
    render(<ResultsPanel runId="run-bad" />);
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeTruthy());
  });
});
```

- [ ] **Step 3: Run ResultsPanel tests**

```bash
cd frontend && npm run test -- --run components/__tests__/ResultsPanel 2>&1 | tail -15
```

Expected: all 3 pass.

- [ ] **Step 4: Delete old card components and their tests**

```bash
rm frontend/components/RegimeCard.tsx
rm frontend/components/DirectionCard.tsx
rm frontend/components/SummaryPanel.tsx
rm frontend/components/__tests__/RegimeCard.test.tsx
rm frontend/components/__tests__/DirectionCard.test.tsx
```

- [ ] **Step 5: Run full test suite**

```bash
cd frontend && npm run test -- --run 2>&1 | tail -25
```

Expected: all tests pass, no references to the deleted files.

- [ ] **Step 6: Type check**

```bash
cd frontend && npm run type-check 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/ResultsPanel.tsx frontend/components/__tests__/ResultsPanel.test.tsx
git rm frontend/components/RegimeCard.tsx frontend/components/DirectionCard.tsx frontend/components/SummaryPanel.tsx frontend/components/__tests__/RegimeCard.test.tsx frontend/components/__tests__/DirectionCard.test.tsx
git commit -m "feat: wire ResultsPanel to ResultsTabs; remove old card components"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| 5 tabs: Overview, Features, Drift, Backtest, Summary | Tasks 3–7 |
| Persistent icon sidebar in sync with tab bar | Task 8 |
| Typed `DriftResult`, `FeatureImportanceResult`, `BacktestResult` | Task 1 |
| `TabPlaceholder` shared component | Task 2 |
| Per-tab placeholder text matches spec | Tasks 3–7 |
| Recharts `BarChart` for Backtest (not LineChart) | Task 6 |
| `ResizeObserver` mock for Recharts in tests | Task 1 |
| Delete old card components | Task 9 |
| Unit tests for each tab + null data path | Tasks 2–8 |
| `ResultsTabs` tab-switching tested | Task 8 |
| `ResultsPanel` updated and tested | Task 9 |

**Placeholder scan:** No TBDs or TODOs present.

**Type consistency:** `AnalysisResult` fields typed in Task 1 are used with the same names in Tasks 3–9. `feature_importance` (not `features`) used consistently. `DriftResult.drifted_features` is `string[]` throughout.

**Note on ResultsPanel current implementation:** The plan assumes `ResultsPanel` currently fetches data internally and accepts a `runId` prop. If the actual current implementation differs, Step 1 of Task 9 must be adapted to match — read the file before editing.
