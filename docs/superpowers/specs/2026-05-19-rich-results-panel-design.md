# Rich Results Panel — Design Spec

## Goal

Replace the current single-column results panel (RegimeCard + DirectionCard + SummaryPanel) with a multi-tab quant-terminal dashboard that surfaces all data the backend already returns: regime distribution, direction distribution, SHAP feature importance, drift diagnostics, backtest performance, and the agent narrative.

## Aesthetic

Quant terminal: dark background (`#07070f`/`#0d0d18`), monospace brand label, compact stat tiles, coloured accent lines on charts. Feels like a Bloomberg terminal or DataDog — data-dense, not a demo.

## Architecture

The layout gains a persistent **icon sidebar** (42 px) to the left of the existing split-pane. The right pane becomes a tabbed panel; the agent timeline pane is unchanged.

```
┌─ TopBar ──────────────────────────────────────────────────────┐
├─ Sidebar ─┬─ Agent pane (250 px) ─┬─ Results pane ───────────┤
│  icons    │  AgentProgressTimeline│  Tab bar                  │
│           │  (unchanged)          │  Tab content (switches)   │
└───────────┴───────────────────────┴───────────────────────────┘
```

## Navigation

**Tab bar** (top of results pane) and **sidebar icons** are in sync — clicking either switches the active tab.

| Icon | Tab | Content |
|------|-----|---------|
| ▦ | Overview | Stat tiles + regime distribution + direction distribution |
| ≡ | Features | Full SHAP importance bar chart (top 10) |
| ⊘ | Drift | PSI tiles + drifted features table + interpretation |
| ↗ | Backtest | Sharpe metrics + cumulative return SVG chart |
| ✎ | Summary | Full agent narrative text |

Tabs with no data (e.g. Backtest in quick mode) show a "not run in this mode" placeholder rather than being hidden — the tab is always visible so the layout is stable.

## Data Sources

All data comes from `AnalysisResult` already returned by `GET /api/runs/{run_id}`. No new backend endpoints needed.

| Tab | Fields used |
|-----|-------------|
| Overview | `regime.{regime, confidence, entropy, distribution}`, `direction.{direction, confidence, distribution, prediction_date}` |
| Features | `feature_importance.{top_features, n_features_evaluated, n_samples_explained}` |
| Drift | `drift.{drift_detected, psi_score, drifted_features, ks_results}` |
| Backtest | `backtest.{regime_accuracy, strategy_sharpe, benchmark_sharpe, n_windows}` |
| Summary | `summary` (string) |

## Components

### New files

| File | Responsibility |
|------|---------------|
| `components/ResultsTabs.tsx` | Tab bar + sidebar icon nav; owns active-tab state; renders the correct page |
| `components/tabs/OverviewTab.tsx` | Stat tiles, regime distribution bars, direction distribution bars |
| `components/tabs/FeaturesTab.tsx` | SHAP horizontal bar chart (top 10 features) |
| `components/tabs/DriftTab.tsx` | PSI stat tiles, drifted features table, interpretation text |
| `components/tabs/BacktestTab.tsx` | Metric tiles (accuracy, strategy Sharpe, benchmark Sharpe), Recharts line chart |
| `components/tabs/SummaryTab.tsx` | Formatted agent narrative |

### Modified files

| File | Change |
|------|--------|
| `app/page.tsx` | Add sidebar to layout; pass `result` down to `ResultsTabs` |
| `components/ResultsPanel.tsx` | Replace card stack with `<ResultsTabs>`; keep skeleton/error/idle states |

### Kept unchanged

`RegimeCard.tsx`, `DirectionCard.tsx`, `SummaryPanel.tsx` — deleted once `ResultsTabs` covers their use cases.

## Tab Designs

### Overview
- Four stat tiles in a row: Regime (abbreviation + full name + confidence %), WTI Direction (arrow + confidence %), Drift status (PSI score + severity), Top signal (feature name + SHAP score)
- Two cards below in a 2-column grid:
  - **Regime probability distribution** — horizontal bar per regime, coloured by regime type (violet = range_bound, amber = geopolitical_spike, green = bull_supercycle, red = bust)
  - **WTI direction distribution** — two thick bars (Down red, Up green)

### Features
- Single full-height card
- One row per feature: right-aligned name (truncated) → bar (width proportional to SHAP value, violet → indigo gradient by rank) → numeric value
- Footer: `n_features_evaluated` features · `n_samples_explained` samples · method label

### Drift
- Three stat tiles: PSI score, count of drifted features, drift detected yes/no
- Drifted features table: feature name | KS statistic | DRIFT badge (amber) or OK badge (slate)
- Interpretation card: plain prose explaining what the drift level means for the regime and directional forecasts

### Backtest
- Three metric boxes: Regime Accuracy (%), Strategy Sharpe, Benchmark Sharpe (SPY)
- Recharts `BarChart` with two grouped bars per metric: Strategy Sharpe vs Benchmark Sharpe, side by side (violet vs slate)
- Separate display of Regime Accuracy as a radial-style percentage or large number tile
- Note: the backend returns aggregate scalars only (`regime_accuracy`, `strategy_sharpe`, `benchmark_sharpe`, `n_windows`) — no per-window time series, so a line chart is not possible without backend changes
- If `backtest` is null: placeholder card "Backtest not run in quick mode. Switch to Full mode to enable walk-forward evaluation."

### Summary
- Single card with the full `summary` string rendered as readable prose (sans-serif font, generous line height, `<strong>` for bolded terms the agent already wraps in `**`)

## Styling

Follows existing Tailwind conventions (`dark:bg-[#0f0f1a]`, `border-slate-800`, etc.). New colour tokens needed:

| Purpose | Class |
|---------|-------|
| Regime purple | `text-violet-400`, `bg-violet-950` |
| Drift amber | `text-amber-400`, `bg-amber-950` |
| Up green | `text-emerald-400` |
| Down red | `text-red-400` |
| Sidebar active | `bg-violet-950 text-violet-400` |

## Placeholder States

Tabs with missing backend data show a consistent "not available" card rather than an empty or broken view. The tab is always present in the nav — the layout never shifts based on what the agent called.

### Why data may be absent

| Field | Reason absent |
|-------|--------------|
| `feature_importance` | Agent skipped `evaluate_features` (quick mode without explicit task) |
| `drift` | Agent skipped `detect_drift` |
| `backtest` | Agent skipped `backtest` (quick mode default) |
| `regime` / `direction` | Agent failed before `run_tabpfn` |

### Placeholder component

A shared `<TabPlaceholder>` component renders in place of any tab whose data is null:

```tsx
<TabPlaceholder
  icon="≡"
  title="Feature importance not available"
  reason="Run in Full mode, or add 'evaluate_features' to tasks."
/>
```

Design: centred in the tab content area, icon large and dim, title in `text-slate-400`, reason in `text-slate-600 text-xs`. No error colour — this is expected, not a failure.

### Per-tab placeholder text

| Tab | Title | Reason shown |
|-----|-------|--------------|
| Features | Feature importance not available | Not computed in this run. Enable in Full mode or add `evaluate_features` to tasks. |
| Drift | Drift analysis not available | Not computed in this run. Enable in Full mode or add `detect_drift` to tasks. |
| Backtest | Backtest not available | Not run in quick mode. Switch to Full mode to enable walk-forward evaluation. |
| Overview | Analysis incomplete | Regime or direction result missing — the run may have failed mid-way. |

## Error Handling

- `feature_importance`, `drift`, `backtest` are all `unknown` in the current `AnalysisResult` type — typed properly as nullable objects in this work
- No tab is ever hidden — the nav structure is always stable regardless of which tools the agent called

## Testing

- Unit tests for each tab component using `@testing-library/react` + `vitest`
- Each test renders the component with realistic fixture data and asserts key text/structure is present
- Null-data path tested for Features, Drift, and Backtest tabs
- `ResultsTabs` tab-switching tested: clicking each tab renders the correct child
