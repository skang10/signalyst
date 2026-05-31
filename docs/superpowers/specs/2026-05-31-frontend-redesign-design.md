# Frontend Redesign — Design Spec

**Date:** 2026-05-31
**Branch:** feat/agent-redesign
**Status:** Design approved — ready for implementation planning

---

## Overview

Complete frontend rebuild aligned with the backend session-based redesign (`docs/backend-redesign.md`). The current frontend is built against the old run-based API and will be replaced. The new frontend models the full session lifecycle: creation → data gathering → user review → analysis → results → follow-up.

**Visual style:** Bloomberg-style dark — navy/charcoal backgrounds (`#060b14`, `#111827`, `#1f2937`), blue accents (`#1d4ed8`, `#3b82f6`), tight typography, data-dense metric cards, professional financial tool aesthetic throughout.

---

## Architecture Approach

**Selective salvage** — the existing tab component shells (`BacktestTab`, `DriftTab`, `FeaturesTab`, `OverviewTab`, `SummaryTab`) map well to the new Results sub-page and are worth keeping as starting points. Everything else is replaced:

| File | Action |
|---|---|
| `lib/api.ts` | Rewrite — replace run-based types/endpoints with session API |
| `lib/store.ts` | Rewrite — replace `useRunStore` with `useSessionStore` |
| `lib/websocket.ts` | Rewrite — replace `useRunStream` with `useSessionStream` |
| `app/page.tsx` | Rewrite — home page |
| `components/TopBar.tsx` | Adapt → becomes the top nav in `sessions/[id]/layout.tsx` and `app/page.tsx` |
| `components/AgentStream.tsx` | Replace with activity feed entries |
| `components/ChatPanel.tsx` | Replace with inline chat in Activity sub-page |
| `components/ResultsPanel.tsx` | Replace with Results sub-page |
| `components/ResultsTabs.tsx` | Replace — tabs are now sub-pages |
| `components/tabs/*.tsx` | Keep shells, adapt to new data shapes |
| `components/AgentDrawer.tsx` | Delete |
| `components/AgentProgressTimeline.tsx` | Delete |
| `components/ThoughtStream.tsx` | Delete |

---

## Routing

Two top-level pages. Session detail uses Next.js App Router nested routes with a shared layout.

```
/                              → Home (session list + indicators)
/sessions/[id]/                → redirect → /sessions/[id]/activity
/sessions/[id]/layout.tsx      → shared: nav, session header, stage strip, tab bar, WS + store
/sessions/[id]/activity/       → Activity sub-page (default)
/sessions/[id]/data/           → Data sub-page
/sessions/[id]/results/        → Results sub-page
```

---

## Home Page — `/`

### Layout
1. **Live indicators strip** — 4 metric cards fetched from `GET /api/market/snapshot` on page load:
   - WTI Crude (CL=F) — price + % change
   - GPR Index — value + % change (amber warning if elevated)
   - EIA Inventory Change — weekly build/draw in Mbbl
   - US Dollar Index (DXY) — price + % change
2. **Latest session banner** — shown only if at least one session with `stage = FOLLOW_UP` exists. Displays the most recent such session (first row by `created_at DESC`). Blue border card with: profile + timeframe, regime badge, direction badge, Sharpe badge, drift badge, one-line agent summary. "Open session →" link.
3. **Sessions table** — columns: Profile, Timeframe, Regime, Stage badge, Status dot, Last Updated, "Open →" link. Rows sorted by `created_at DESC`. Failed/old rows shown at reduced opacity.
4. **"+ NEW ANALYSIS" button** — top-right in nav bar, opens New Analysis modal.

### New Analysis Modal
Fields: Market Profile (dropdown from `GET /api/profiles`), Start Date, End Date, Auto Mode toggle (skip USER_REVIEW gate).

On submit: `POST /api/sessions` → `{ session_id }` → navigate to `/sessions/[id]/activity`.

---

## Shared Session Layout — `app/sessions/[id]/layout.tsx`

Rendered on all three sub-pages. Owns:
- WebSocket connection to `WS /ws/sessions/{id}/stream`
- Session state (`useSessionStore`) — fetched via `GET /api/sessions/{id}` on mount, live-updated via WS
- All navigation chrome

### Chrome elements (top to bottom)
1. **Top nav** — SIGNALYST logo (blue square dot + wordmark) + "+ NEW ANALYSIS" button
2. **Session header** — "← Sessions" back link, profile name, timeframe, stage+status badge. Cancel button visible only when `status = RUNNING`.
3. **Stage progress strip** — 7 segments (CONFIG → DATA → REVIEW → FEATURES → ANALYZE → EXPLAIN → FOLLOW-UP). Green = done, blue + pulse = active, gray = pending. Stage labels below each segment.
4. **Tab bar** — Activity · Data · Results. Lock/unlock rules:

| Stage | Activity | Data | Results |
|---|---|---|---|
| CONFIGURING | active | locked | locked |
| DATA_GATHERING | active | locked | locked |
| USER_REVIEW | waiting (chat on) | unlocked | locked |
| FEATURIZING | active | unlocked | locked |
| ANALYZING | active | unlocked | locked |
| EXPLAINING | active | unlocked | locked |
| FOLLOW_UP | waiting (chat on) | unlocked | **unlocked ✦** |

Results tab shows a `✦` marker when it first unlocks. Data tab shows `✓` once DATA_GATHERING completes.

---

## Activity Sub-page — `/sessions/[id]/activity`

### Concept
A **single continuous feed** that accumulates across all stages. Stage dividers separate phases. Stream entries log agent thoughts and tool calls in real time. Gate messages appear at the bottom when the pipeline reaches an interactive stage. The user always has the full history visible — nothing is lost when transitioning from running to review.

**Feed data source:** on page load, the feed is reconstructed from `session.conversation` (the append-only history stored in the DB, returned by `GET /api/sessions/{id}`). Live WS messages (`wsMessages` from `useSessionStore`) are appended on top as they arrive. On reconnect, the feed is re-hydrated from `conversation` — live stream entries from already-completed stages are not lost.

### Feed entry types

```
Stage divider:   ── DATA GATHERING · completed in 18s ──
Done entry:      ✓  Fetched CL=F [fetch_yfinance pill] — 126 rows · 0% missing
Active entry:    ⚙  Computing lag features (63 features)...
Pending entry:   ◦  TabPFN classification
Warning entry:   ⚠  Drift detected — CL=F_roc_20d (PSI 0.23)
Tool pill:       [fetch_yfinance] (inline in entry text, monospace blue border)
```

### USER_REVIEW gate message
Appears at the bottom of the feed when stage = USER_REVIEW. Contains:
- "Data ready — N rows × N series" heading
- Brief agent description of what was fetched
- **Inline featurizer config editor** (Option B — editable tags):
  - Windows row: removable tags (e.g. `5d ×`, `20d ×`, `60d ×`) + `+ add` input
  - Lags row: removable tags + `+ add` input
  - Feature families row: toggleable tags (active = blue, disabled = strikethrough grey)
  - Feature count estimate updates live (e.g. `≈ 187 features planned`)
  - "View full data manifest →" link to Data sub-page
- Chat input enabled (placeholder: "Add a source, adjust config, or ask a question…")
- "Run Analysis →" primary button — calls `POST /sessions/{id}/proceed`
- Config changes sent via `POST /sessions/{id}/chat` → ReviewInterpreter patches `featurizer_config`

### FOLLOW_UP gate message
Appears at the bottom of the feed when stage = FOLLOW_UP. Contains:
- "Analysis complete" heading
- Regime, direction, Sharpe, drift result badges
- One-line agent summary
- "View full results →" link to Results sub-page
- Chat input enabled (placeholder: "Ask a follow-up question…")
- Responses from FollowUpAgent appear as chat bubbles in the feed

### Chat input state
| Stage | Chat input |
|---|---|
| Active stages | Disabled, placeholder: "Chat available at data review and follow-up…" |
| USER_REVIEW | Enabled + "Run Analysis →" button visible |
| FOLLOW_UP | Enabled, no action button |

---

## Data Sub-page — `/sessions/[id]/data`

Unlocks after DATA_GATHERING completes. Read-only reference view.

### Layout
1. **Header row** — "Data Manifest" title + optional cache badge (`⚡ Cached from session #N`) if `cache_hit = true`
2. **4 metric cards** — Rows, Series, Missing % (green if < 1%, amber if > 1%), Features (count after featurizing, once available)
3. **Sources grid** — one chip per data source: connector name (bold), missing % (green/amber), source label (yfinance / EIA API / Federal Reserve / FRED API)
4. **Time series sparklines** — one per key series, WTI (CL=F) always shown first. Filled area chart, blue stroke, min/mean/max/σ labels below.

No chat input on this page — all interaction happens in Activity.

---

## Results Sub-page — `/sessions/[id]/results`

Unlocks after EXPLAINING completes. Full analysis output in one scrollable page.

### Layout (top to bottom)

**Row 1 — 4 metric cards** (left accent border color indicates signal)
- Regime — amber border. Regime label + confidence bar
- WTI Direction (4w) — green border. ↑/↓ + confidence bar
- Strategy Sharpe — blue border. Value + "vs SPY N.NN · N% accuracy"
- Drift — amber border if detected, green if clean. PSI and feature name

**Row 2 — 2-column**
- Left (wider): WTI price chart with regime overlay. Shaded amber rectangle for geo-spike region, dashed vertical line at regime start, region label. Price sparkline in blue. Min/mean/max labels.
- Right: SHAP top signals horizontal bar chart. Feature name + bar (blue, indigo for lower-ranked) + value. Up to 8 features shown.

**Row 3 — 2-column**
- Left: Walk-forward backtest chart. Headline metrics (Strategy Sharpe, SPY Sharpe, Accuracy) above a cumulative returns line chart (strategy = green solid, SPY = gray dashed). Legend below.
- Right: Drift detection table. Each row: feature name + PSI score + ✓ or ⚠. Flagged features (PSI > 0.20) at top, bold amber.

**Row 4 — Agent summary**
Full-width card. Agent narrative prose (1-4 paragraphs). Regime, direction, and key signals styled inline (amber/blue emphasis). Generated by ExplanationAgent during EXPLAINING stage; streams in when first available.

---

## State Management

### `useSessionStore` (replaces `useRunStore`)

```typescript
type SessionStore = {
  sessionId: string | null
  stage: SessionStage | null
  status: SessionStatus | null
  featurizerConfig: FeaturizerConfig | null
  conversation: ChatMessage[]        // full conversation history
  wsMessages: WsMessage[]            // live stream entries (capped at 500)
  artifacts: {
    data: DataArtifactRef[]
    features: FeatureArtifactRef[]
    analysis: AnalysisResultRef[]
  }
  error: string | null
}
```

### `useSessionStream(sessionId)` (replaces `useRunStream`)

Connects to `WS /ws/sessions/{id}/stream`. On each message:
- `stage_transition` → update `stage`, `status`, navigate if needed
- `thought` / `tool_call` / `tool_result` → append to `wsMessages`
- `artifact_ready` → update `artifacts`, refresh artifact data
- `cache_hit` → update artifact with provenance
- `done` → update `status = WAITING`
- `error` → update `error`

On mount: fetch `GET /api/sessions/{id}` to populate initial state, then connect WS.
On disconnect: reconnect with exponential backoff; re-fetch session state on reconnect.

---

## API Client — `lib/api.ts`

Replace all existing types and endpoints. Key new types:

```typescript
type Session = { session_id, market_profile, timeframe_start, timeframe_end, stage, status, error, auto, featurizer_config, conversation, artifacts, stage_history }
type MarketSnapshot = { wti, brent, dxy, gpr, eia_inventory_change_mmbbl, fetched_at }
type DataArtifact = { kind: 'data', artifact_id, round, sources, data_manifest, cache_hit, cached_from_session_id }
type AnalysisResult = { kind: 'analysis', artifact_id, regime, direction, feature_importance, drift, backtest, summary, cache_hit }
```

New endpoints wired:
```
GET  /api/market/snapshot
POST /api/sessions
GET  /api/sessions
GET  /api/sessions/{id}
POST /api/sessions/{id}/proceed
POST /api/sessions/{id}/chat
POST /api/sessions/{id}/rerun
POST /api/sessions/{id}/cancel
GET  /api/sessions/{id}/artifacts/{artifact_id}
GET  /api/profiles
```

---

## Component Map

### New files
| File | Purpose |
|---|---|
| `app/page.tsx` | Home page |
| `app/sessions/[id]/layout.tsx` | Shared session chrome + store + WS |
| `app/sessions/[id]/activity/page.tsx` | Activity feed |
| `app/sessions/[id]/data/page.tsx` | Data manifest |
| `app/sessions/[id]/results/page.tsx` | Results dashboard |
| `components/SessionIndicators.tsx` | Live market indicators strip |
| `components/LatestSessionBanner.tsx` | Latest session result banner |
| `components/SessionsTable.tsx` | Sessions list table |
| `components/NewAnalysisModal.tsx` | New analysis form modal |
| `components/StageStrip.tsx` | 7-segment progress strip |
| `components/ActivityFeed.tsx` | Continuous feed with entries + gate messages |
| `components/FeedEntry.tsx` | Single feed entry (done/active/pending/warn) |
| `components/GateMessage.tsx` | USER_REVIEW and FOLLOW_UP gate cards |
| `components/FeaturizerConfigEditor.tsx` | Inline editable tags for windows/lags/families |
| `components/ChatInput.tsx` | Chat input row (disabled/enabled states) |
| `lib/store.ts` | `useSessionStore` |
| `lib/websocket.ts` | `useSessionStream` |
| `lib/api.ts` | Session-based API client |

### Adapted files (keep, update types + data)
| File | Adapts to |
|---|---|
| `components/tabs/BacktestTab.tsx` | Results backtest section |
| `components/tabs/DriftTab.tsx` | Results drift section |
| `components/tabs/FeaturesTab.tsx` | Results SHAP section |
| `components/tabs/OverviewTab.tsx` | Results metric cards |
| `components/tabs/SummaryTab.tsx` | Results agent summary |

---

## Design Tokens (Bloomberg-style)

```
bg-base:       #060b14   page background
bg-surface:    #111827   nav, cards at rest
bg-elevated:   #1f2937   card interiors, inputs
bg-deep:       #111827   code/stream background

border:        #21262d   nav borders
border-subtle: #1f2937   card borders, dividers
border-muted:  #374151   input borders, inactive strips

accent-blue:   #1d4ed8   buttons, active tab, tool pills
accent-light:  #3b82f6   charts, SHAP bars, links
accent-muted:  #60a5fa   active stage labels, agent messages

text-primary:  #f9fafb
text-secondary:#9ca3af
text-muted:    #6b7280
text-disabled: #4b5563

green:         #22c55e   done, bullish, ok
amber:         #f59e0b   regime spike, drift, warnings
red:           #ef4444   failed, bearish
indigo:        #6366f1   lower-ranked SHAP bars
```

---

## New Backend Endpoint Required

`GET /api/market/snapshot` — documented in `docs/backend-redesign.md`. Thin yfinance + FRED fetch, no session dependency. Used exclusively by the home page indicators strip.

---

## Out of Scope

- Authentication (JWT + NextAuth.js) — separate mid-tier spec
- Derivatives Panel (Phase 2)
- Satellite imagery signals (Phase 2)
- Mobile/responsive layout — desktop-only for now
- Save & export (PDF, CSV, shareable link)
