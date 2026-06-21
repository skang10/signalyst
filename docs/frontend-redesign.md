# Signalyst Frontend — Current Architecture

**Status:** Implemented. This document describes the frontend as it exists today (session-based UI on `app/sessions/[id]/*`). For the history of how it got here, see the dated specs/plans under `docs/superpowers/specs/` and `docs/superpowers/plans/`.

---

## Visual style

Light theme: white backgrounds, `gray-900` text, `gray-200` borders. A single `--color-brand` CSS variable drives the primary accent (buttons, active tab, links, chart lines), set in `app/globals.css`:

- Default (`:root`): green — `--color-brand: #059669`, hover `#047857`, soft bg `#ecfdf5`, soft border `#a7f3d0`
- `[data-theme="gold"]`: amber — `--color-brand: #d97706`, hover `#b45309`, soft bg `#fffbeb`, soft border `#fde68a`

Theme choice is toggled via `components/ThemeToggle.tsx`, persisted to `localStorage` (`signalyst-theme`), and applied via a `data-theme` attribute on `<html>` (set early by an inline script in `app/layout.tsx` to avoid a flash of the wrong theme).

Status colors are plain Tailwind: `green-*` (done/bullish), `amber-*` (warnings/drift), `red-*` (failed/bearish), `gray-*` (neutral/disabled).

---

## Routing

```
/                              → Home (sessions table + live indicators + new analysis modal)
/sessions/[id]/layout.tsx      → shared chrome: header, session status bar, sidebar nav, stage strip, WS + store
/sessions/[id]/activity/       → Activity feed (default landing after creating a session)
/sessions/[id]/config/         → Data Connectors — editable session config (timeframe, sources, featurizer)
/sessions/[id]/data/           → Data Status — read-only data manifest / series preview
/sessions/[id]/overview/       → Results: regime, direction, Sharpe, drift summary cards
/sessions/[id]/features/       → Results: SHAP feature importance
/sessions/[id]/backtest/        → Results: walk-forward backtest chart
```

---

## Home Page — `/`

- Header: "■ Signalyst" wordmark + "+ New Analysis" button (`bg-brand`)
- `SessionIndicators` — live market snapshot strip from `GET /api/market/snapshot` (WTI, Brent, DXY, GPR, EIA inventory change)
- `SessionsTable` — sessions list from `GET /api/sessions`, supports multi-select + bulk delete (`DELETE /api/sessions/{id}`)
- `NewAnalysisModal` — Market Profile (from `GET /api/profiles`), Start/End Date, Auto Mode toggle → `POST /api/sessions` → navigate to `/sessions/[id]/activity`

---

## Shared Session Layout — `app/sessions/[id]/layout.tsx`

Rendered on all session sub-pages. Owns:
- `useSessionStream(id)` — WebSocket connection to `/ws/sessions/{id}/stream`
- Session state (`useSessionStore`), fetched via `GET /api/sessions/{id}` on mount and polled every 3s while `status = running`
- Header bar: wordmark + "+ New Analysis" link
- Status bar: "← Sessions" link, session id (short), stage badge (`bg-brand-soft`/`text-brand`), status indicator (running/waiting/failed/canceled), Cancel button when `status = running`
- `SessionSidebar` — left nav (see below)
- `StageStrip` — horizontal progress strip across the 7 stages

### `SessionSidebar` nav and lock rules

```
Navigation
  Activity        — always available
  Config          — always available
  Data Status     — locked while stage ∈ {configuring, data_gathering}

Results
  Overview        — locked unless stage = follow_up
  Features        — locked unless stage = follow_up
  Backtest        — locked unless stage = follow_up
```

Locked items render as disabled text with a 🔒 icon and a tooltip.

---

## Activity Sub-page — `/sessions/[id]/activity`

Continuous feed grouped by stage (`lib/activity-groups.ts` → `buildGroups`), reconstructed from `session.activity_events` + `session.conversation` on load and updated live via WS messages (`wsMessages`).

- **Stage pills** — one per stage, status-colored: active (`bg-brand-soft`/`text-brand`, pulsing dot), failed (red), done (green)
- **Tool pills** — inline labels for tool calls (`fetch_yfinance`, `fetch_fred`, `fetch_eia`, `fetch_gpr`, `fetch_custom_connector`, `http_get`/`http_post`, `save_connector_spec`, `approve_sources`, etc.), formatted by `TOOL_DISPLAY` in the page
- **User review gate** (`components/GateMessage.tsx` → `UserReviewGate`) — appears when `stage = user_review`: inline `FeaturizerConfigEditor`, config changes saved via `PATCH /api/sessions/{id}/config`, "Run Analysis →" calls `POST /api/sessions/{id}/proceed`
- **Chat input** — enabled at `user_review` and `follow_up`; sends via `POST /api/sessions/{id}/chat` (90s timeout — LLM calls can be slow)

---

## Config (Data Connectors) Sub-page — `/sessions/[id]/config`

Foldable card sections, all editable except where noted:

1. **Session** — market profile (read-only badge), timeframe start/end date inputs (disabled while running)
2. **Data Connectors** — `ConnectorEditor` showing available connectors (`GET /api/connectors`, SPEC-type connectors filtered out — see CLAUDE.md), grouped chip grid of `pending_sources`, plus `UploadRow` for CSV/Parquet upload (`POST /api/sessions/{id}/upload`, merge or replace mode)
3. **Featurizer** — `FeaturizerConfigEditor` (windows/lags/feature_families/energy_specific), editable only while `stage = user_review`

Dirty-state bar (Save/Discard) appears when local edits differ from the session; Save calls `PATCH /api/sessions/{id}/config` then refetches the session. A staleness banner (`lib/stale.ts` → `isSessionStale`) appears if the timeframe or sources have changed since the last data fetch, with a "Re-run from data →" button (`POST /api/sessions/{id}/rerun` with `stage: "data_gathering"`).

---

## Data Status Sub-page — `/sessions/[id]/data`

Read-only. Metric cards (rows, series, missing %, features), `visibleTickers` source chips, time-series sparklines from `DataArtifactDetail.series_preview` (via `GET /api/sessions/{id}/artifacts/{artifact_id}`). Shows `StaleResultsBanner` if the config has drifted from the artifact that produced the current results.

---

## Results Sub-pages — Overview / Features / Backtest

Unlocked at `stage = follow_up`. Each is a thin page wrapping the corresponding tab component:
- `overview` → `components/tabs/OverviewTab.tsx` — regime, direction, Sharpe, drift metric cards + WTI price/regime chart
- `features` → `components/tabs/FeaturesTab.tsx` — SHAP feature importance bar chart
- `backtest` → `components/tabs/BacktestTab.tsx` — walk-forward cumulative returns chart vs SPY

`components/tabs/DriftTab.tsx` and `components/tabs/SummaryTab.tsx` are fully built (drift table, agent narrative summary) but unused — no route or nav entry imports them. `TabPlaceholder.tsx` is the fallback for locked/empty states.

---

## State Management — `lib/store.ts`

```typescript
type SessionStore = {
  sessionId: string | null
  stage: SessionStage | null
  status: SessionStatus | null
  marketProfile: string | null
  timeframeStart: string | null
  timeframeEnd: string | null
  pendingSources: PendingSource[]
  featurizerConfig: FeaturizerConfig | null
  conversation: ChatMessage[]
  activityEvents: ActivityEvent[]
  wsMessages: WsMessage[]            // live stream entries, capped at 500
  artifacts: SessionArtifacts        // { data, features, analysis }
  error: string | null

  setSession: (session: Session) => void
  appendWsMessage: (msg: WsMessage) => void
  clearSession: () => void
}
```

## WebSocket — `lib/websocket.ts` → `useSessionStream(sessionId)`

Connects to `WS /ws/sessions/{id}/stream` with exponential backoff reconnect (1s → 30s). On `stage_transition`, `artifact_ready`, or `error` messages, refetches `GET /api/sessions/{id}` to resync store state; all messages are appended to `wsMessages`.

---

## API Client — `lib/api.ts`

Key types: `Session`, `SessionListItem`, `SessionStage`, `SessionStatus`, `FeaturizerConfig`, `PendingSource`, `ConnectorOut`, `SessionArtifacts` (`DataArtifactRef` / `FeatureArtifactRef` / `AnalysisResultRef`), `ChatMessage`, `ActivityEvent`, `StageHistoryEntry`, `MarketProfile`, `MarketSnapshot`, `DataArtifactDetail`.

Endpoints wired:
```
GET    /api/market/snapshot
GET    /api/profiles
GET    /api/connectors
POST   /api/sessions
GET    /api/sessions
GET    /api/sessions/{id}
DELETE /api/sessions/{id}
POST   /api/sessions/{id}/proceed
POST   /api/sessions/{id}/chat
POST   /api/sessions/{id}/rerun
POST   /api/sessions/{id}/cancel
PATCH  /api/sessions/{id}/config
POST   /api/sessions/{id}/upload
GET    /api/sessions/{id}/artifacts/{artifact_id}
```

---

## Out of Scope

- Authentication (JWT + NextAuth.js) — separate mid-tier spec
- Derivatives Panel (Phase 2)
- Satellite imagery signals (Phase 2)
- Mobile/responsive layout — desktop-only for now
- Save & export (PDF, CSV, shareable link)
- Connector builder UI — backend `ConnectorBuilderAgent` quality gate not yet proven (see `CLAUDE.md`)
