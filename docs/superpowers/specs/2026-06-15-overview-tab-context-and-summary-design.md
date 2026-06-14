# Overview Tab: Market Context Header + Summary Panel + Generalized Regime Labels

## Problem

The Overview tab (`frontend/components/tabs/OverviewTab.tsx`) was recently wired to render
real `AnalysisResult` data (regime, direction, drift, top signal). Two gaps remain:

1. The LLM-generated `summary` field is fetched (`AnalysisResultDetail.summary`) but never
   displayed.
2. Now that market profiles have been generalized to `oil`, `sp500`, and `eurusd`
   (see `backend/src/db/seed.py`), nothing on the Overview tab tells the user which market
   the session is analyzing or what problem the analysis solves. Additionally,
   `REGIME_LABELS` and the distribution-bar colors in `OverviewTab` are hardcoded to oil's
   regime vocabulary (`bull_supercycle`, `bust`, `geopolitical_spike`), so sessions for
   `sp500`/`eurusd` render raw snake_case regime names (`bull_market`, `uptrend`, etc.) and
   default-colored bars.

## Goals

- Add a market context header to the Overview tab showing the active `MarketProfile`'s
  `name` and `description`.
- Render the analysis `summary` text in a new panel.
- Generalize regime label formatting and distribution-bar coloring so they work correctly
  for all market profiles, not just oil.

## Non-Goals

- No changes to the backend API (the `/api/profiles` and
  `/api/sessions/{id}/analysis/{artifact_id}` endpoints already return everything needed).
- No changes to Features/Backtest tabs.
- No changes to how `MarketProfile.regime_labels` ordering is defined or seeded.

## Design

### 1. Market context header

`frontend/app/sessions/[id]/overview/page.tsx`:
- Add a third fetch effect: `api.getProfiles()` on mount, find the entry whose `id` matches
  `marketProfile` (from `useSessionStore()`), store it in
  `const [profile, setProfile] = useState<MarketProfile | null>(null)`.
- Pass `profile={profile}` to `<OverviewTab>`.

`OverviewTab.tsx`:
- New optional prop `profile?: MarketProfile | null` (reuse the existing `MarketProfile`
  type from `lib/api.ts`: `{ id, name, description, default_connectors,
  default_featurizer_config, regime_labels }`).
- At the top of the rendered output (above the stat tile grid), render a header block when
  `profile` is present:
  - `profile.name` as a bold title (e.g. "Oil Markets")
  - `profile.description` as muted subtext (e.g. "WTI/Brent crude oil regime analysis using
    macro, geopolitical, and energy signals.")
- If `profile` is null (still loading or fetch failed), render nothing extra — existing
  layout is unaffected.

### 2. Generalized regime labels and colors

`OverviewTab.tsx`:
- Remove the static `REGIME_LABELS` dict.
- Add a helper:

```ts
function formatRegimeLabel(regime: string): string {
  return regime
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
```

  - `bull_market` → "Bull Market", `range_bound` → "Range Bound",
    `geopolitical_spike` → "Geopolitical Spike". (Existing test uses the regex
    `/range.bound/i`, which matches "Range Bound" with a space.)
- Replace both `REGIME_LABELS[regime.regime] ?? regime.regime` and
  `REGIME_LABELS[r] ?? r` with `formatRegimeLabel(regime.regime)` / `formatRegimeLabel(r)`.

- Add a helper for distribution-bar color, using the regime's position in
  `profile.regime_labels` (each profile's array is ordered
  `[bullish, range_bound, bearish, volatility_spike]` per `seed.py`):

```ts
const REGIME_POSITION_COLORS = [
  "bg-emerald-600", // index 0: bullish
  "bg-brand",        // index 1: range-bound / neutral
  "bg-red-600",      // index 2: bearish
  "bg-amber-500",    // index 3: volatility spike
];

function regimeColor(regime: string, profile?: MarketProfile | null): string {
  const idx = profile?.regime_labels.indexOf(regime) ?? -1;
  return REGIME_POSITION_COLORS[idx] ?? "bg-brand";
}
```

- Replace the existing inline ternary chain (`r === "bull_supercycle" ? ... : r === "bust"
  ? ... `) in the regime distribution `DistBar` color prop with `regimeColor(r, profile)`.

### 3. Summary panel

`OverviewTab.tsx`:
- New panel rendered below the existing "Regime Distribution" / "Direction Distribution"
  grid:

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

- `AnalysisResult` type in `OverviewTab.tsx` gains `summary?: string | null`.
- Hidden entirely when `summary` is null/empty — no placeholder needed.

## Testing

- `OverviewTab.test.tsx`:
  - Update existing regime-label assertions if needed (regex already tolerant of the space
    vs. hyphen change).
  - New test: passing `profile` with `name`/`description` renders both strings.
  - New test: passing `result.summary` renders the summary text in a "Summary" panel;
    omitting it renders no such panel.
  - New test: regime distribution bar color reflects position in `profile.regime_labels`
    (e.g. a `sp500` profile with `regime_labels = ["bull_market", "range_bound",
    "bear_market", "high_volatility"]` colors `bear_market` red).
- `OverviewPage` (`overview/page.tsx`) currently has no dedicated test file; a lightweight
  test is optional — covered implicitly by `OverviewTab` tests plus existing type-checking.
  Confirm via `npm run type-check`.

## Files Touched

- `frontend/components/tabs/OverviewTab.tsx` (modify)
- `frontend/components/tabs/__tests__/OverviewTab.test.tsx` (modify)
- `frontend/app/sessions/[id]/overview/page.tsx` (modify)
