# Light Theme Redesign Implementation Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the dark theme with a clean white light theme using an OpenAI-docs-inspired layout and teal accent color, making the UI feel natively designed for light rather than color-inverted from dark.

**Scope:** All frontend files — `app/`, `components/`. No backend changes. No dark-mode toggle; light-only.

---

## Design Decisions

### Color Palette

| Role | Token (Tailwind) | Hex |
|---|---|---|
| Page background | `bg-white` | `#ffffff` |
| Surface / panel | `bg-gray-50` | `#f9fafb` |
| Subtle surface | `bg-gray-100` | `#f3f4f6` |
| Border default | `border-gray-200` | `#e5e7eb` |
| Border subtle | `border-gray-100` | `#f3f4f6` |
| Text primary | `text-gray-900` | `#111827` |
| Text secondary | `text-gray-500` | `#6b7280` |
| Text tertiary | `text-gray-400` | `#9ca3af` |
| **Accent** | `text-teal-600` / `bg-teal-600` | `#0d9488` |
| Accent light bg | `bg-teal-50` | `#f0fdfa` |
| Accent border | `border-teal-200` | `#99f6e4` |
| Success | `text-green-600` / `bg-green-50` / `border-green-200` | semantic |
| Error | `text-red-600` / `bg-red-50` / `border-red-200` | semantic |
| Warning | `text-amber-500` | semantic |
| Info (running state) | `text-blue-600` / `bg-blue-50` / `border-blue-200` | semantic |

The existing purple gradient on agent avatars and user chat bubbles is replaced by solid teal (`#0d9488`).

### Layout

**OpenAI-docs-inspired:** top bar → stage strip → two-column body (wide sidebar + main content).

- **Top bar** (`h-12`): logo left, `+ New Analysis` button right (teal fill on home, outline on session detail). Session breadcrumb (id, stage pill, status) sits between them on session detail pages.
- **Stage strip** (`h-8`): thin progress bar below the top bar, `bg-gray-50` background, completed stages in `text-green-600`, active stage in `text-teal-600` with `border-b-2 border-teal-600`, future stages in `text-gray-400`.
- **Sidebar** (`w-44`, `bg-white`, `border-r border-gray-200`): grouped nav with uppercase `text-gray-400` section labels (`text-[10px] tracking-widest`), nav items as plain text `text-gray-700`, active item gets `bg-gray-100 text-gray-900 font-semibold rounded-md`.
- **Main content** (`bg-white`): unchanged layout internally, just re-skinned.

### Typography

System font stack (`-apple-system, BlinkMacSystemFont, "Inter", sans-serif`) already used implicitly; make explicit in `globals.css`. Slightly increased line-height for chat bubbles (`leading-relaxed`).

### Component-level changes

**`globals.css`**
- Body: `bg-white text-gray-900`, drop the current `bg-[#0f0f1a]`.

**`app/layout.tsx` (root)**
- Remove any remaining dark body class.

**`app/page.tsx` (sessions list)**
- `bg-white` page, clean top bar with teal `+ New Analysis` button.
- `SessionsTable` gets light table styles: `bg-white` rows, `hover:bg-gray-50`, `border-gray-100` row borders, teal stage pills, teal `Open →` links, semantic status dots.

**`app/sessions/[id]/layout.tsx` (session shell)**
- Top bar: `bg-white border-gray-200`, logo in `text-gray-900`, breadcrumb with teal stage pill (`bg-teal-50 text-teal-600 border-teal-200`), `Cancel` button keeps `border-red-400 text-red-500`.
- `ReviewBanner`: `bg-blue-50 border-blue-200 text-blue-700` (was `bg-[#0a1628] border-[#1d4ed8]`).
- Main wrapper: `bg-gray-50` outer, `border-gray-200` card border.

**`components/StageStrip.tsx`**
- `bg-gray-50 border-gray-200`, completed `text-green-600 border-b-green-500`, active `text-teal-600 border-b-teal-600`, inactive `text-gray-400`.

**`components/SessionSidebar.tsx`**
- `bg-white border-gray-200`, section labels `text-gray-400 uppercase tracking-widest`, items `text-gray-600 hover:text-gray-900 hover:bg-gray-50`, active `bg-gray-100 text-gray-900 font-semibold`.

**`app/sessions/[id]/activity/page.tsx`**
- Stage pills: done → `bg-green-50 border-green-200 text-green-700`; active → `bg-teal-50 border-teal-200 text-teal-600`; failed → `bg-red-50 border-red-200 text-red-600`.
- Agent avatar: solid `bg-teal-600` circle (replaces blue-to-purple gradient).
- Agent speech bubble: `bg-gray-50 border-gray-100 text-gray-900 shadow-sm`.
- User bubble: solid `bg-teal-600 text-white` (replaces blue-to-purple gradient).
- `AgentThinkingLine`: `text-gray-400`, animated dot in `bg-teal-400`.
- Tool chips: `bg-white border-gray-200 text-gray-600`, expanded detail `bg-gray-50`.
- `ThinkingBlock`: `border-gray-200`, active left border `border-teal-400`.
- Completion chips: keep semantic colors (green `artifact_ready`, purple `cache_hit` → teal).
- Input bar: `bg-white border-gray-200`, input field `bg-gray-50 border-gray-200 focus:border-teal-400`, send button `bg-teal-600 hover:bg-teal-700`.
- `showRunAnalysis` button area: `bg-teal-600` proceed button.

**`app/sessions/[id]/config/page.tsx`**, **`data/page.tsx`**, **`results/page.tsx`**
- Page backgrounds `bg-white`, headings `text-gray-900`, body text `text-gray-600`, borders `border-gray-200`.

**`components/NewAnalysisModal.tsx`**
- `bg-white border-gray-200 shadow-xl`, inputs `bg-white border-gray-300 focus:border-teal-500`, submit `bg-teal-600 hover:bg-teal-700 text-white`.

**`components/GateMessage.tsx`** / **`components/FeaturizerConfigEditor.tsx`**
- Backgrounds `bg-gray-50`, borders `border-gray-200`, accent elements `text-teal-600` / `border-teal-500`.

**`components/SessionIndicators.tsx`**
- Status bar: `bg-white border-gray-200`, running indicator `text-green-600`, dots teal.

**`components/tabs/`** (BacktestTab, DriftTab, FeaturesTab, OverviewTab, SummaryTab)
- Cards `bg-white border-gray-200 shadow-sm`, chart/table text `text-gray-700`, section headers `text-gray-900 font-semibold`.

### Shadows instead of dark borders

Where the dark theme used dark-colored borders to create separation (`border-[#21262d]`), the light theme uses `shadow-sm` on floating elements (bubbles, cards, modals) and `border-gray-100`/`border-gray-200` for structural separation. This is what makes light themes feel "native" rather than inverted.

---

## Files Touched

| File | Change type |
|---|---|
| `frontend/app/globals.css` | body background + font |
| `frontend/app/page.tsx` | full re-skin |
| `frontend/app/sessions/[id]/layout.tsx` | full re-skin |
| `frontend/app/sessions/[id]/activity/page.tsx` | full re-skin (largest file) |
| `frontend/app/sessions/[id]/config/page.tsx` | re-skin |
| `frontend/app/sessions/[id]/data/page.tsx` | re-skin |
| `frontend/app/sessions/[id]/results/page.tsx` | re-skin |
| `frontend/components/StageStrip.tsx` | re-skin |
| `frontend/components/SessionSidebar.tsx` | re-skin |
| `frontend/components/SessionsTable.tsx` | re-skin |
| `frontend/components/SessionIndicators.tsx` | re-skin |
| `frontend/components/NewAnalysisModal.tsx` | re-skin |
| `frontend/components/GateMessage.tsx` | re-skin |
| `frontend/components/FeaturizerConfigEditor.tsx` | re-skin |
| `frontend/components/tabs/*.tsx` | re-skin (5 files) |
| `frontend/tailwind.config.ts` | add teal to safelist if needed |

---

## Approach

**Option B — Tailwind built-in classes.** Replace every hardcoded hex value (`bg-[#...]`, `text-[#...]`, `border-[#...]`) with the equivalent standard Tailwind class per the color mapping table above. No new CSS variables or custom tokens. Classes are readable and the mapping is mechanical once the palette is fixed.

---

## Out of Scope

- Dark mode toggle
- Changes to backend
- Changes to test files (unless a test asserts a specific class name that changes)
- Recharts chart colors (left as-is; chart libraries handle their own theming)
