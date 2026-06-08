# Light Theme Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dark Tailwind theme with a clean white light theme using teal (`#0d9488`) as the accent color and an OpenAI-docs-inspired layout.

**Architecture:** Replace every hardcoded hex Tailwind class with a standard Tailwind class per the palette mapping in the spec. No new CSS custom properties, no component restructuring, no dark-mode toggle. Pure re-skin: 16 files, ~312 hex values replaced.

**Tech Stack:** Next.js 15, Tailwind CSS 4, TypeScript. Dev server: `cd frontend && npm run dev`.

**Color mapping cheatsheet:**
- `bg-[#0f0f1a]`/`bg-[#060b14]`/`bg-[#0d1117]`/`bg-[#070b11]`/`bg-[#020c05]`/`bg-[#0d0d18]` → `bg-white` or `bg-gray-50`
- `bg-[#111827]`/`bg-[#0a1628]`/`bg-[#0d0d18]` → `bg-white` (top bars) or `bg-gray-50` (panels)
- `bg-[#1f2937]` → `bg-gray-100` (hover states) or `bg-gray-50` (speech bubble)
- `border-[#21262d]`/`border-[#1f2937]`/`border-slate-800` → `border-gray-200`
- `border-[#374151]` → `border-gray-300` (inputs) or `border-gray-200`
- `text-[#f9fafb]`/`text-slate-100`/`text-slate-200`/`text-slate-300` → `text-gray-900` or `text-gray-700`
- `text-[#9ca3af]`/`text-slate-400` → `text-gray-400`
- `text-[#6b7280]`/`text-[#4b5563]`/`text-slate-500`/`text-slate-600` → `text-gray-500`
- `text-[#374151]` → `text-gray-300` (dim) or `text-gray-400`
- `text-[#3b82f6]`/`text-[#60a5fa]`/`bg-[#1d4ed8]`/`bg-[#2563eb]` → `text-teal-600`/`bg-teal-600`/`bg-teal-700`
- `text-[#22c55e]`/`bg-[#22c55e]` → `text-green-600`/`bg-green-500` (semantic, keep)
- `text-[#ef4444]`/`bg-[#ef4444]` → `text-red-500`/`bg-red-500` (semantic, keep)
- `text-[#f59e0b]`/`bg-[#f59e0b]` → `text-amber-500` (semantic, keep)
- Stage pill active: `bg-[#1f2937] text-[#60a5fa] border-[#1d4ed8]` → `bg-teal-50 text-teal-600 border-teal-200`
- Stage pill done: `bg-[#052e16] text-[#22c55e] border-[#14532d]` → `bg-green-50 text-green-700 border-green-200`
- Stage pill failed: `bg-[#1a0505] text-[#f97316] border-[#7c2d12]` → `bg-red-50 text-red-600 border-red-200`
- Cache hit: `bg-[#1e1040] border-[#4c1d95] text-[#a78bfa]` → `bg-teal-50 border-teal-200 text-teal-600`
- Tab components `text-violet-400`/`bg-violet-600` → `text-teal-600`/`bg-teal-600`
- Linear gradient avatars → solid `bg-teal-600`
- ReviewBanner: `bg-[#0a1628] border-[#1d4ed8]` → `bg-blue-50 border-blue-200`, text `text-[#93c5fd]` → `text-blue-700`

---

### Task 1: globals.css and home page shell

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Rewrite globals.css**

```css
@import "tailwindcss";

body {
  @apply bg-white text-gray-900;
  font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
}
```

- [ ] **Step 2: Rewrite app/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { NewAnalysisModal } from "@/components/NewAnalysisModal";
import { SessionIndicators } from "@/components/SessionIndicators";
import { SessionsTable } from "@/components/SessionsTable";
import { api } from "@/lib/api";
import type { SessionListItem } from "@/lib/api";

export default function Home() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [showModal, setShowModal] = useState(false);

  const refresh = () => {
    api.getSessions().then(setSessions).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-white text-gray-900">
      <header className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <span className="font-bold text-gray-900 text-base tracking-tight">■ Signalyst</span>
        <button
          onClick={() => setShowModal(true)}
          className="text-sm px-3 py-1 rounded bg-teal-600 hover:bg-teal-700 text-white font-semibold transition-colors"
        >
          + New Analysis
        </button>
      </header>

      <SessionIndicators />

      <main className="flex-1 px-4 py-4">
        <h1 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Sessions</h1>
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <SessionsTable sessions={sessions} onDelete={refresh} />
        </div>
      </main>

      {showModal && (
        <NewAnalysisModal
          onClose={() => {
            setShowModal(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css frontend/app/page.tsx
git commit -m "feat: light theme — base styles and home page shell"
```

---

### Task 2: SessionsTable

**Files:**
- Modify: `frontend/components/SessionsTable.tsx`

- [ ] **Step 1: Rewrite SessionsTable.tsx**

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import type { SessionListItem, SessionStage, SessionStatus } from "@/lib/api";

const STAGE_LABELS: Record<SessionStage, string> = {
  configuring: "Config",
  data_gathering: "Data",
  user_review: "Review",
  featurizing: "Features",
  analyzing: "Analyze",
  explaining: "Explain",
  follow_up: "Follow-up",
};

const STATUS_DOT: Record<SessionStatus, string> = {
  running: "bg-green-500 animate-pulse",
  waiting: "bg-gray-400",
  failed: "bg-red-500",
  canceled: "bg-amber-500",
};

type Props = { sessions: SessionListItem[]; onDelete: () => void };

export function SessionsTable({ sessions, onDelete }: Props) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm("Delete this session? This cannot be undone.")) return;
    setDeletingId(sessionId);
    try {
      await api.deleteSession(sessionId);
      onDelete();
    } catch {
      // swallow — row stays visible if delete fails
    } finally {
      setDeletingId(null);
    }
  };

  if (sessions.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
        No sessions yet — create your first analysis above
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-gray-500 text-xs uppercase tracking-wider">
          <th className="text-left px-4 py-2">Profile</th>
          <th className="text-left px-4 py-2">Timeframe</th>
          <th className="text-left px-4 py-2">Stage</th>
          <th className="text-left px-4 py-2">Status</th>
          <th className="text-left px-4 py-2">Last Updated</th>
          <th className="px-4 py-2" />
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr
            key={s.session_id}
            className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
          >
            <td className="px-4 py-3 text-gray-900 font-medium capitalize">{s.market_profile}</td>
            <td className="px-4 py-3 text-gray-500 font-mono text-xs">
              {s.timeframe_start} → {s.timeframe_end}
            </td>
            <td className="px-4 py-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-600 border border-teal-200">
                {STAGE_LABELS[s.stage] ?? s.stage}
              </span>
            </td>
            <td className="px-4 py-3">
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${STATUS_DOT[s.status]}`} />
                <span className="text-gray-500 capitalize">{s.status}</span>
              </div>
            </td>
            <td className="px-4 py-3 text-gray-400 text-xs">
              {new Date(s.updated_at).toLocaleString()}
            </td>
            <td className="px-4 py-3">
              <div className="flex items-center justify-end gap-3">
                <Link
                  href={`/sessions/${s.session_id}/activity`}
                  className="text-teal-600 hover:text-teal-700 text-xs transition-colors"
                >
                  Open →
                </Link>
                <button
                  onClick={() => handleDelete(s.session_id)}
                  disabled={deletingId === s.session_id}
                  className="text-gray-400 hover:text-red-500 text-xs transition-colors disabled:opacity-40"
                  aria-label="Delete session"
                >
                  {deletingId === s.session_id ? "Deleting…" : "Delete"}
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/SessionsTable.tsx
git commit -m "feat: light theme — SessionsTable"
```

---

### Task 3: SessionIndicators

**Files:**
- Modify: `frontend/components/SessionIndicators.tsx`

- [ ] **Step 1: Rewrite SessionIndicators.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MarketSnapshot } from "@/lib/api";

function IndicatorCard({
  label,
  value,
  changePct,
  warn,
}: {
  label: string;
  value: string;
  changePct: number | null;
  warn?: boolean;
}) {
  const changeColor =
    changePct === null
      ? "text-gray-500"
      : changePct >= 0
        ? "text-green-600"
        : "text-red-500";

  return (
    <div
      className={[
        "flex-1 px-3 py-2 rounded border bg-white",
        warn ? "border-amber-400" : "border-gray-200",
      ].join(" ")}
    >
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-base font-mono text-gray-900">{value}</div>
      {changePct !== null && (
        <div className={`text-xs ${changeColor}`}>
          {changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

export function SessionIndicators() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);

  useEffect(() => {
    api.getMarketSnapshot().then(setSnapshot).catch(() => {});
  }, []);

  return (
    <div className="flex gap-2 px-4 py-3 border-b border-gray-200">
      <IndicatorCard
        label="WTI Crude"
        value={snapshot?.wti ? `$${snapshot.wti.price.toFixed(2)}` : "—"}
        changePct={snapshot?.wti?.change_pct ?? null}
      />
      <IndicatorCard
        label="Brent"
        value={snapshot?.brent ? `$${snapshot.brent.price.toFixed(2)}` : "—"}
        changePct={snapshot?.brent?.change_pct ?? null}
      />
      <IndicatorCard
        label="DXY"
        value={snapshot?.dxy ? snapshot.dxy.price.toFixed(1) : "—"}
        changePct={snapshot?.dxy?.change_pct ?? null}
      />
      <IndicatorCard
        label="GPR Index"
        value={snapshot?.gpr ? snapshot.gpr.value.toFixed(1) : "—"}
        changePct={snapshot?.gpr?.change_pct ?? null}
        warn={(snapshot?.gpr?.value ?? 0) > 200}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/SessionIndicators.tsx
git commit -m "feat: light theme — SessionIndicators"
```

---

### Task 4: StageStrip + SessionSidebar

**Files:**
- Modify: `frontend/components/StageStrip.tsx`
- Modify: `frontend/components/SessionSidebar.tsx`

- [ ] **Step 1: Rewrite StageStrip.tsx**

```tsx
"use client";

import type { SessionStage } from "@/lib/api";

const STAGES: { key: SessionStage; label: string }[] = [
  { key: "configuring", label: "CONFIG" },
  { key: "data_gathering", label: "DATA" },
  { key: "user_review", label: "REVIEW" },
  { key: "featurizing", label: "FEATURES" },
  { key: "analyzing", label: "ANALYZE" },
  { key: "explaining", label: "EXPLAIN" },
  { key: "follow_up", label: "FOLLOW-UP" },
];

const STAGE_ORDER = STAGES.map((s) => s.key);

type Props = { currentStage: SessionStage | null };

export function StageStrip({ currentStage }: Props) {
  const currentIdx = currentStage ? STAGE_ORDER.indexOf(currentStage) : -1;

  return (
    <div className="flex items-center px-4 py-2 border-b border-gray-200 bg-gray-50 gap-1">
      {STAGES.map((stage, idx) => {
        const isDone = idx < currentIdx;
        const isActive = idx === currentIdx;
        const isPending = idx > currentIdx;

        return (
          <div key={stage.key} className="flex flex-col items-center flex-1">
            <div
              className={[
                "h-1 w-full rounded-full",
                isDone ? "bg-green-500" : "",
                isActive ? "bg-teal-500 animate-pulse" : "",
                isPending ? "bg-gray-200" : "",
              ].join(" ")}
            />
            <span
              className={[
                "text-[10px] mt-1 font-mono tracking-wider",
                isDone ? "text-green-600" : "",
                isActive ? "text-teal-600" : "",
                isPending ? "text-gray-400" : "",
              ].join(" ")}
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite SessionSidebar.tsx**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Config", path: "config" },
  { label: "Results", path: "results" },
];

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";

export function SessionSidebar({
  sessionId,
  stage,
}: {
  sessionId: string;
  stage: string | null;
}) {
  const pathname = usePathname();

  return (
    <nav className="w-[170px] flex-shrink-0 flex flex-col gap-1 p-2.5 border-r border-gray-200">
      {TABS.map((tab) => {
        const href = `/sessions/${sessionId}/${tab.path}`;
        const isActive = pathname === href;

        const isLocked =
          (tab.path === "data" && stage !== null && DATA_LOCKED_STAGES.has(stage)) ||
          (tab.path === "results" && stage !== RESULTS_UNLOCKED_STAGE);

        const badge =
          tab.path === "data" && stage !== null && !DATA_LOCKED_STAGES.has(stage)
            ? " ✓"
            : tab.path === "results" && stage === RESULTS_UNLOCKED_STAGE
            ? " ✦"
            : "";

        if (isLocked) {
          return (
            <span
              key={tab.label}
              title="Locked — not available at this stage"
              className="flex items-center justify-between px-3 py-2 rounded text-sm text-gray-300 cursor-not-allowed select-none"
            >
              {tab.label}
              <span aria-hidden>🔒</span>
            </span>
          );
        }

        return (
          <Link
            key={tab.label}
            href={href}
            className={[
              "px-3 py-2 rounded text-sm transition-colors",
              isActive
                ? "bg-gray-100 text-gray-900 font-semibold"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-50",
            ].join(" ")}
          >
            {tab.label}
            {badge}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/StageStrip.tsx frontend/components/SessionSidebar.tsx
git commit -m "feat: light theme — StageStrip and SessionSidebar"
```

---

### Task 5: NewAnalysisModal

**Files:**
- Modify: `frontend/components/NewAnalysisModal.tsx`

- [ ] **Step 1: Rewrite NewAnalysisModal.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { MarketProfile } from "@/lib/api";

type Props = { onClose: () => void };

export function NewAnalysisModal({ onClose }: Props) {
  const router = useRouter();
  const [profiles, setProfiles] = useState<MarketProfile[]>([]);
  const [profileId, setProfileId] = useState("oil");
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [autoMode, setAutoMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getProfiles().then(setProfiles).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await api.createSession({
        market_profile: profileId,
        timeframe_start: start,
        timeframe_end: end,
        auto: autoMode,
      });
      router.push(`/sessions/${session_id}/activity`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-white border border-gray-200 rounded-lg p-6 w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">New Analysis</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-lg"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-gray-500 uppercase tracking-wider">Market Profile</span>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-teal-500"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              {profiles.length === 0 && <option value="oil">Oil Markets</option>}
            </select>
          </label>

          <div className="flex gap-3">
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-gray-500 uppercase tracking-wider">Start</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-teal-500"
              />
            </label>
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-gray-500 uppercase tracking-wider">End</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-teal-500"
              />
            </label>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoMode}
              onChange={(e) => setAutoMode(e.target.checked)}
              className="w-4 h-4 accent-teal-600"
            />
            <span className="text-sm text-gray-500">Auto mode (skip user review gate)</span>
          </label>

          {error && <p className="text-xs text-red-500">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 py-2 rounded bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-sm font-semibold text-white transition-colors"
          >
            {loading ? "Starting…" : "Start Analysis"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/NewAnalysisModal.tsx
git commit -m "feat: light theme — NewAnalysisModal"
```

---

### Task 6: FeaturizerConfigEditor + GateMessage

**Files:**
- Modify: `frontend/components/FeaturizerConfigEditor.tsx`
- Modify: `frontend/components/GateMessage.tsx`

- [ ] **Step 1: Rewrite FeaturizerConfigEditor.tsx**

Replace the 5 style constants and the checkbox at the bottom. Complete file:

```tsx
"use client";

import { useState } from "react";
import type { FeaturizerConfig } from "@/lib/api";

const FAMILY_LABELS: Record<string, string> = {
  rolling_stats: "Rolling Stats",
  momentum: "Momentum",
  lag: "Lag",
  regime: "Regime",
};

type Props = {
  value: FeaturizerConfig;
  onChange?: (next: FeaturizerConfig) => void;
  readOnly?: boolean;
};

const TAG_ACTIVE =
  "px-2 py-0.5 bg-teal-50 border border-teal-300 rounded text-xs text-teal-700 hover:bg-teal-100";
const TAG_INACTIVE =
  "px-2 py-0.5 bg-transparent border border-gray-300 rounded text-xs text-gray-400 line-through hover:border-gray-400";
const TAG_READONLY =
  "px-2 py-0.5 bg-transparent border border-gray-200 rounded text-xs text-gray-500";
const ADD_INPUT =
  "w-14 bg-transparent border border-dashed border-gray-300 rounded px-2 py-0.5 text-xs text-gray-500 placeholder:text-gray-400 focus:outline-none focus:border-teal-400";
const ROW_LABEL = "text-[10px] text-gray-500 w-16 flex-shrink-0";

function NumberRow({
  label,
  values,
  unit,
  onAdd,
  onRemove,
  readOnly,
}: {
  label: string;
  values: number[];
  unit: string;
  onAdd: (n: number) => void;
  onRemove: (n: number) => void;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const n = Number(draft);
    if (Number.isInteger(n) && n > 0 && !values.includes(n)) onAdd(n);
    setDraft("");
  };

  if (readOnly) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>{label}</span>
        {values.map((v) => (
          <span key={`${label}-${v}`} className={TAG_READONLY}>
            {v}
            {unit}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={ROW_LABEL}>{label}</span>
      {values.map((v) => (
        <button key={`${label}-${v}`} onClick={() => onRemove(v)} className={TAG_ACTIVE}>
          {v}
          {unit} ×
        </button>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        placeholder="+ add"
        className={ADD_INPUT}
      />
    </div>
  );
}

export function FeaturizerConfigEditor({ value, onChange, readOnly = false }: Props) {
  const setWindows = (windows: number[]) => onChange?.({ ...value, windows });
  const setLags = (lags: number[]) => onChange?.({ ...value, lags });

  const toggleFamily = (key: string) => {
    if (readOnly) return;
    onChange?.({
      ...value,
      feature_families: value.feature_families.includes(key)
        ? value.feature_families.filter((f) => f !== key)
        : [...value.feature_families, key],
    });
  };

  return (
    <div className="flex flex-col gap-2.5">
      <NumberRow
        label="WINDOWS"
        values={value.windows}
        unit="d"
        onAdd={(n) => setWindows([...value.windows, n].sort((a, b) => a - b))}
        onRemove={(n) => setWindows(value.windows.filter((w) => w !== n))}
        readOnly={readOnly}
      />
      <NumberRow
        label="LAGS"
        values={value.lags}
        unit="d"
        onAdd={(n) => setLags([...value.lags, n].sort((a, b) => a - b))}
        onRemove={(n) => setLags(value.lags.filter((l) => l !== n))}
        readOnly={readOnly}
      />
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>FAMILIES</span>
        {Object.entries(FAMILY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggleFamily(key)}
            className={[
              value.feature_families.includes(key) ? TAG_ACTIVE : TAG_INACTIVE,
              readOnly ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-xs text-gray-500">
        <input
          type="checkbox"
          checked={value.energy_specific}
          onChange={(e) => onChange?.({ ...value, energy_specific: e.target.checked })}
          disabled={readOnly}
          className="accent-teal-600"
        />
        Energy-specific features
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite GateMessage.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { FeaturizerConfigEditor } from "./FeaturizerConfigEditor";
import type { FeaturizerConfig } from "@/lib/api";

function arraysEqual<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function configsEqual(a: FeaturizerConfig, b: FeaturizerConfig): boolean {
  return (
    arraysEqual(a.windows, b.windows) &&
    arraysEqual(a.lags, b.lags) &&
    arraysEqual(a.feature_families, b.feature_families) &&
    a.energy_specific === b.energy_specific
  );
}

type UserReviewGateProps = {
  serverConfig: FeaturizerConfig;
  onProceed: (patch?: FeaturizerConfig) => void;
  proceeding: boolean;
  onDirtyChange: (dirty: boolean) => void;
};

export function UserReviewGate({
  serverConfig,
  onProceed,
  proceeding,
  onDirtyChange,
}: UserReviewGateProps) {
  const [draft, setDraft] = useState(serverConfig);
  const [syncedConfig, setSyncedConfig] = useState(serverConfig);
  const isDirty = !configsEqual(draft, serverConfig);

  if (!configsEqual(syncedConfig, serverConfig)) {
    setSyncedConfig(serverConfig);
    setDraft(serverConfig);
  }

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  return (
    <div className="self-end max-w-[85%] flex flex-col gap-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
      <FeaturizerConfigEditor value={draft} onChange={setDraft} />

      {isDirty && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
          <span className="flex-1">Config changed — Run Analysis to apply, or discard your edits</span>
          <button onClick={() => setDraft(serverConfig)} className="text-amber-600 hover:underline">
            Discard
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onProceed(isDirty ? draft : undefined)}
          disabled={proceeding}
          className="px-4 py-2 bg-teal-600 border border-teal-700 rounded-full text-white text-sm font-semibold hover:bg-teal-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {proceeding ? "Starting…" : "→ Run Analysis"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/FeaturizerConfigEditor.tsx frontend/components/GateMessage.tsx
git commit -m "feat: light theme — FeaturizerConfigEditor and GateMessage"
```

---

### Task 7: Session layout

**Files:**
- Modify: `frontend/app/sessions/[id]/layout.tsx`

- [ ] **Step 1: Rewrite layout.tsx**

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { SessionSidebar } from "@/components/SessionSidebar";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

function ReviewBanner({ sessionId }: { sessionId: string }) {
  const { conversation, status } = useSessionStore();
  const pathname = usePathname();
  const activityHref = `/sessions/${sessionId}/activity`;

  if (pathname === activityHref) return null;

  const lastMsg = conversation[conversation.length - 1];
  const hasAgentReply = lastMsg?.role === "assistant";

  let hint: string;
  let linkText: string;
  if (status === "running") {
    hint = "· Agent is thinking…";
    linkText = "view in Activity →";
  } else if (hasAgentReply) {
    hint = "· Agent replied —";
    linkText = "go to Activity to respond →";
  } else {
    hint = "· Satisfied with the data?";
    linkText = "Go to Activity to proceed →";
  }

  return (
    <div className="flex items-center gap-2 px-4 py-1.5 bg-blue-50 border-b border-blue-200 text-xs flex-shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />
      <span className="text-blue-700">{hint}</span>
      <Link href={activityHref} className="text-blue-600 underline underline-offset-2">
        {linkText}
      </Link>
    </div>
  );
}

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { sessionId, stage, status, setSession } = useSessionStore();
  const [canceling, setCanceling] = useState(false);

  useSessionStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    api
      .getSession(id)
      .then(setSession)
      .catch(() => router.push("/"));
  }, [id, router, setSession]);

  useEffect(() => {
    if (!id || status !== "running") return;
    const interval = setInterval(() => {
      api.getSession(id).then(setSession).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [id, status, setSession]);

  const handleCancel = async () => {
    if (!id) return;
    setCanceling(true);
    try {
      await api.cancelSession(id);
      const updated = await api.getSession(id);
      setSession(updated);
    } catch {
      // swallow — status will update on next poll/WS event
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <span className="font-bold text-gray-900 text-base tracking-tight">■ Signalyst</span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-gray-200 text-gray-500 hover:text-gray-900 transition-colors"
        >
          + New Analysis
        </Link>
      </header>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white">
        <Link href="/" className="text-gray-500 hover:text-gray-900 text-sm transition-colors">
          ← Sessions
        </Link>
        {sessionId && (
          <>
            <span className="text-gray-300 text-xs">·</span>
            <span className="text-sm text-gray-500 font-mono">{id?.slice(0, 8)}</span>
            {stage && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-600 border border-teal-200">
                {stage}
              </span>
            )}
            {status && (
              <span
                className={[
                  "text-xs",
                  status === "running" ? "text-green-600" : "",
                  status === "waiting" ? "text-gray-500" : "",
                  status === "failed" ? "text-red-500" : "",
                  status === "canceled" ? "text-amber-500" : "",
                ].join(" ")}
              >
                {status === "running" && "● "}
                {status}
              </span>
            )}
            {status === "running" && (
              <button
                onClick={handleCancel}
                disabled={canceling}
                className="ml-auto text-xs px-2 py-0.5 rounded border border-red-400 text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40"
              >
                {canceling ? "Canceling…" : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>

      <StageStrip currentStage={stage} />

      {stage === "user_review" && id && <ReviewBanner sessionId={id} />}

      <div className="flex-1 min-h-0 m-4 flex border border-gray-200 rounded-lg overflow-hidden bg-white">
        {id && <SessionSidebar sessionId={id} stage={stage} />}
        <main className="flex-1 overflow-auto min-h-0">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add "frontend/app/sessions/[id]/layout.tsx"
git commit -m "feat: light theme — session layout"
```

---

### Task 8: activity/page.tsx

This is the largest file (~500 lines). Work through it component by component.

**Files:**
- Modify: `frontend/app/sessions/[id]/activity/page.tsx`

- [ ] **Step 1: Update StagePill styles (lines 42–62)**

Replace the 3 `styles` objects inside `StagePill`:

```tsx
  const styles =
    group.status === "active"
      ? { wrap: "border-teal-200 bg-teal-50 text-teal-600", dot: "bg-teal-500 animate-pulse" }
      : group.status === "failed"
      ? { wrap: "border-red-200 bg-red-50 text-red-600", dot: "bg-red-500" }
      : { wrap: "border-green-200 bg-green-50 text-green-700", dot: "bg-green-500" };
```

- [ ] **Step 2: Update ThinkingBlock (lines 66–91)**

Replace the outer `div` border, button hover, text colors, spinner, expand toggle, and thought text:

```tsx
function ThinkingBlock({ thoughts, active }: { thoughts: ThoughtEntry[]; active: boolean }) {
  const [open, setOpen] = useState(active);

  return (
    <div className="border border-gray-200 rounded-r-lg overflow-hidden" style={{ borderLeftWidth: 2, borderLeftColor: active ? "#0d9488" : "#9ca3af" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="text-xs text-gray-400">💭</span>
        <span className="text-xs text-gray-400 uppercase tracking-wider flex-1">thinking</span>
        {active && <span className="text-teal-600 text-xs animate-spin leading-none">⟳</span>}
        <span className="text-gray-300 text-xs">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="px-3 pb-2 flex flex-col gap-1 border-t border-gray-100">
          {thoughts.map((t) => (
            <p key={t.id} className="text-xs text-gray-400 italic leading-relaxed">
              {t.content}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update ToolChip (lines 95–131)**

```tsx
function ToolChip({ row }: { row: FetchRow }) {
  const [open, setOpen] = useState(false);
  const ready = row.result !== null;
  const label = toolLabel(row.tool, row.input);

  return (
    <div className="rounded-md overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full px-3 py-1.5 bg-white border border-gray-200 rounded-md text-left hover:border-gray-300 transition-colors"
      >
        <span className="text-gray-400 text-xs">⚙</span>
        <span className="text-xs text-gray-500 flex-1 truncate">{label}</span>
        <span className={`text-xs flex-shrink-0 ${ready ? "text-green-600" : "text-teal-500 animate-pulse"}`}>
          {ready ? "→ ready" : "fetching…"}
        </span>
      </button>
      {open && (
        <div className="border border-t-0 border-gray-100 rounded-b-md px-3 py-1.5 space-y-1 bg-gray-50">
          <div className="text-xs font-mono">
            <span className="text-gray-300">in </span>
            <span className="text-gray-500 break-all">{JSON.stringify(row.input)}</span>
          </div>
          {row.result && (
            <div className="text-xs font-mono">
              <span className="text-gray-300">out </span>
              <span className="text-gray-500 break-all">
                {JSON.stringify(row.result).slice(0, 300)}
                {JSON.stringify(row.result).length > 300 ? "…" : ""}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Update CompletionChip (lines 135–176)**

```tsx
function CompletionChip({ event }: { event: Record<string, unknown> }) {
  if (event.type === "artifact_ready") {
    const kind = event.kind as string;
    if (kind === "sources") {
      const connectors = (event.connectors as string[] | undefined) ?? [];
      return (
        <div className="inline-flex items-center gap-1.5 self-start px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs text-green-700">
          ✓ {connectors.length} source{connectors.length !== 1 ? "s" : ""} configured
          {connectors.length > 0 && (
            <span className="text-green-600">
              ({connectors.slice(0, 4).join(", ")}{connectors.length > 4 ? ` +${connectors.length - 4}` : ""})
            </span>
          )}
        </div>
      );
    }
    if (kind === "data") return null;
    if (kind === "features") {
      return (
        <div className="inline-flex self-start px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs text-green-700">
          ✓ {event.n_features as number} features · {event.n_rows as number} rows
        </div>
      );
    }
    if (kind === "analysis") {
      const regime = event.regime as string | undefined;
      return (
        <div className="inline-flex self-start px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs text-green-700">
          ✓ Analysis complete{regime ? ` · ${regime}` : ""}
        </div>
      );
    }
  }
  if (event.type === "cache_hit") {
    return (
      <div className="inline-flex self-start px-3 py-1 bg-teal-50 border border-teal-200 rounded-full text-xs text-teal-600">
        ⚡ cache hit
      </div>
    );
  }
  return null;
}
```

- [ ] **Step 5: Update AgentSpeechBubble (lines 180–200)**

```tsx
function AgentSpeechBubble({ content }: { content: string }) {
  return (
    <div className="flex gap-3">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5 bg-teal-600"
      >
        S
      </div>
      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <span className="text-xs text-gray-500 font-medium">Signalyst Agent</span>
        <div
          className="bg-gray-50 border border-gray-200 px-3 py-2 text-sm text-gray-900 leading-relaxed shadow-sm"
          style={{ borderRadius: "2px 12px 12px 12px" }}
        >
          {content}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Update DataCompletionChip (lines 204–248)**

```tsx
function DataCompletionChip({
  event,
  cacheHitEvent,
}: {
  event: Record<string, unknown>;
  cacheHitEvent: Record<string, unknown> | null;
}) {
  const [open, setOpen] = useState(false);
  const rows = event.rows as number | undefined;
  const tickers = (event.tickers as string[] | undefined) ?? [];
  const cachedAt = cacheHitEvent?.cached_from_created_at as string | undefined;

  return (
    <div className="self-start rounded-md overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 border border-green-200 rounded-md text-xs text-green-700 hover:border-green-300 transition-colors"
      >
        <span>✓ {rows} rows · {tickers.length} signal{tickers.length !== 1 ? "s" : ""}</span>
        {cacheHitEvent && (
          <span className="px-1.5 py-0.5 bg-teal-50 border border-teal-200 rounded-full text-teal-600">
            ⚡ cached
          </span>
        )}
        <span className="text-green-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="border border-t-0 border-green-200 rounded-b-md px-3 py-2 bg-white flex flex-col gap-2">
          <div className="flex flex-wrap gap-1">
            {tickers.map((t) => (
              <span key={t} className="px-1.5 py-0.5 bg-green-50 border border-green-200 rounded text-xs text-green-700 font-mono">
                {t}
              </span>
            ))}
          </div>
          {cachedAt && (
            <p className="text-xs text-teal-600">
              ⚡ Originally fetched {new Date(cachedAt).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Update AgentTurn avatar + error chip (lines 252–303)**

In `AgentTurn`, replace the avatar `style` prop and error div:

```tsx
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5 bg-teal-600"
      >
        S
      </div>
```

```tsx
        {/* label */}
        <span className="text-xs text-gray-500 font-medium">Signalyst Agent</span>
```

```tsx
        {group.errorEvent && (
          <div className="text-xs text-red-600 px-3 py-1.5 bg-red-50 border border-red-200 rounded-md">
            ✕ {(group.errorEvent.message as string) ?? "unknown error"}
          </div>
        )}
```

- [ ] **Step 8: Update AgentThinkingLine (lines 307–325)**

```tsx
function AgentThinkingLine() {
  return (
    <div className="flex gap-3">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5 bg-teal-600"
      >
        S
      </div>
      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <span className="text-xs text-gray-500 font-medium">Signalyst Agent</span>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <span className="text-teal-600 animate-spin leading-none">⟳</span>
          <span>Thinking…</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 9: Update UserBubble (lines 329–340)**

```tsx
function UserBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div
        className="bg-teal-600 text-white px-3 py-2 text-sm leading-relaxed max-w-[75%]"
        style={{ borderRadius: "12px 12px 4px 12px" }}
      >
        {msg.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 10: Update ActivityPage shell, input bar, and empty state (lines 415–500)**

Empty state:
```tsx
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
```

Input bar wrapper:
```tsx
        <div className="border-t border-gray-200 bg-white px-4 py-3 flex flex-col gap-1.5 flex-shrink-0">
```

Input field:
```tsx
              className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-teal-400 disabled:opacity-40"
```

Send button:
```tsx
              className="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
```

Error:
```tsx
          {sendError && <p className="text-xs text-red-500">{sendError}</p>}
```

- [ ] **Step 11: Commit**

```bash
git add "frontend/app/sessions/[id]/activity/page.tsx"
git commit -m "feat: light theme — activity page"
```

---

### Task 9: config/page.tsx and results/page.tsx

**Files:**
- Modify: `frontend/app/sessions/[id]/config/page.tsx`
- Modify: `frontend/app/sessions/[id]/results/page.tsx`

- [ ] **Step 1: Update config/page.tsx color classes**

Replace these 6 occurrences:
- `text-[#4b5563]` → `text-gray-400` (loading state)
- `text-[#9ca3af]` (read-only label, saving label) → `text-gray-400`
- `text-[#6b7280]` (lock label, note text) → `text-gray-500`
- `text-[#22c55e]` → `text-green-600`
- `text-[#ef4444]` → `text-red-500`

Complete updated file:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import type { FeaturizerConfig } from "@/lib/api";

type SaveStatus = "idle" | "saving" | "saved" | "failed";

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const { featurizerConfig, stage, setSession } = useSessionStore();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [pendingConfig, setPendingConfig] = useState<FeaturizerConfig | null>(null);

  useEffect(() => {
    if (status !== "saved") return;
    const timeout = setTimeout(() => setStatus("idle"), 2000);
    return () => clearTimeout(timeout);
  }, [status]);

  if (!featurizerConfig) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  const handleChange = async (next: FeaturizerConfig) => {
    if (!id) return;
    setStatus("saving");
    setPendingConfig(next);
    try {
      await api.updateConfig(id, next);
      const updated = await api.getSession(id);
      setSession(updated);
      setStatus("saved");
      setPendingConfig(null);
    } catch {
      setStatus("failed");
    }
  };

  const handleRetry = () => {
    if (pendingConfig) handleChange(pendingConfig);
  };

  if (stage !== "user_review") {
    return (
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">Session config — read only</span>
          <span className="text-xs text-gray-500">🔒 locked at this stage</span>
        </div>
        <FeaturizerConfigEditor value={featurizerConfig} readOnly />
        <p className="text-xs text-gray-500">Editable only during the review step.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">Session config — editable while in review</span>
        {status === "saving" && <span className="text-xs text-gray-400">Saving…</span>}
        {status === "saved" && <span className="text-xs text-green-600">✓ Saved</span>}
        {status === "failed" && (
          <span className="text-xs text-red-500 flex items-center gap-2">
            Failed to save
            <button onClick={handleRetry} className="underline underline-offset-2">
              retry
            </button>
          </span>
        )}
      </div>
      <FeaturizerConfigEditor value={featurizerConfig} onChange={handleChange} />
    </div>
  );
}
```

- [ ] **Step 2: Update results/page.tsx**

```tsx
export default function ResultsPage() {
  return (
    <div className="flex items-center justify-center h-full text-gray-400 text-sm">
      Results dashboard — available after analysis completes (PR 4)
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/sessions/[id]/config/page.tsx" "frontend/app/sessions/[id]/results/page.tsx"
git commit -m "feat: light theme — config and results pages"
```

---

### Task 10: data/page.tsx

This file is ~600 lines. Work through each sub-component.

**Files:**
- Modify: `frontend/app/sessions/[id]/data/page.tsx`

- [ ] **Step 1: Update MetricCard**

```tsx
function MetricCard({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`flex-1 px-3 py-2 rounded border bg-white ${warn ? "border-amber-400" : "border-gray-200"}`}
    >
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-mono ${warn ? "text-amber-500" : "text-gray-900"}`}>
        {value}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update DataSnapshotTable — button, pagination, table**

Button:
```tsx
          className="flex items-center gap-1.5 text-xs text-gray-400 uppercase tracking-wider hover:text-gray-600 transition-colors"
```

Pagination text/buttons:
```tsx
            <span className="text-xs text-gray-400">
```
```tsx
              className="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-30 transition-colors px-1"
```

Table `overflow-auto` div:
```tsx
      {open && <div className="overflow-auto rounded border border-gray-200">
```

Table header row:
```tsx
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2 text-gray-400 font-normal whitespace-nowrap">Date</th>
              {tickers.map((ticker) => (
                <th key={ticker} className="text-right px-3 py-2 font-normal whitespace-nowrap">
                  <span className="text-gray-500">{ticker}</span>
                  {(missingPct[ticker] ?? 0) > 0 && (
                    <span className="ml-1 text-amber-500">·{missingPct[ticker]}%</span>
                  )}
                </th>
              ))}
            </tr>
```

Table body rows (alternating):
```tsx
                  className={`border-b border-gray-100 last:border-0 ${
                    i % 2 === 0 ? "bg-white" : "bg-gray-50"
                  }`}
```

Table cells:
```tsx
                  <td className="px-3 py-1.5 text-gray-400">{date}</td>
```
```tsx
                        className={`px-3 py-1.5 text-right ${
                          v == null ? "text-gray-300" : "text-gray-900"
                        }`}
```

- [ ] **Step 3: Update Sparkline SVG colors**

```tsx
      {/* Axis lines */}
      <line x1={mL} y1={mT} x2={mL} y2={mT + cH} stroke="#e5e7eb" strokeWidth="1" />
      <line x1={mL} y1={mT + cH} x2={mL + cW} y2={mT + cH} stroke="#e5e7eb" strokeWidth="1" />

      {/* Y-axis ticks */}
      {yTicks.map(({ val, y }) => (
        <g key={y}>
          <line x1={mL - 3} y1={y} x2={mL} y2={y} stroke="#d1d5db" strokeWidth="1" />
          <text x={mL - 5} y={y + 3} textAnchor="end" fontSize="8" fill="#6b7280" fontFamily="monospace">
            {fmt(val)}
          </text>
        </g>
      ))}

      {/* X-axis labels */}
      <text x={mL} y={H - 3} textAnchor="start" fontSize="8" fill="#6b7280" fontFamily="monospace">
        {firstDate}
      </text>
      <text x={mL + cW} y={H - 3} textAnchor="end" fontSize="8" fill="#6b7280" fontFamily="monospace">
        {lastDate}
      </text>

      {/* Data line */}
      <polyline points={pts} fill="none" stroke="#0d9488" strokeWidth="1.5" />
```

- [ ] **Step 4: Update UploadPanel**

Intro text:
```tsx
          <p className="text-sm text-gray-500 text-center">
```

Drop zone:
```tsx
          className="w-full border-2 border-dashed border-gray-200 hover:border-teal-400 rounded-lg p-8 flex flex-col items-center gap-2 text-gray-500 hover:text-gray-700 transition-colors"
```

File preview box:
```tsx
            <div className="bg-gray-50 border border-gray-200 rounded p-3 flex flex-col gap-1 text-xs">
              <div className="flex gap-4 text-gray-500">
```
```tsx
            <div className="text-gray-400 font-mono truncate">
```

Overlap warning:
```tsx
          <div className="flex gap-2 bg-amber-50 border border-amber-300 rounded p-3 text-xs text-amber-600">
```

Source name input:
```tsx
          className="w-full bg-white border border-gray-200 rounded px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-teal-400"
```

Error:
```tsx
        {error && <p className="text-xs text-red-500">{error}</p>}
```

Primary button (replace / merge / upload):
```tsx
              className="w-full py-2 rounded bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
```

Secondary button (merge anyway / replace):
```tsx
              className="w-full py-1.5 rounded border border-gray-200 text-gray-400 hover:text-gray-700 text-xs transition-colors disabled:opacity-40"
```

- [ ] **Step 5: Update DataPage main render**

h2 title + cache indicator:
```tsx
        <h2 className="text-sm font-semibold text-gray-900">Data Manifest</h2>
        {artifact.cache_hit && <span className="text-xs text-amber-500">⚡ Cached</span>}
```

High-missing warning block:
```tsx
        {stage === "user_review" && avgMissing > MISSING_PCT_LIMIT && (
          <div className="flex items-start gap-3 bg-amber-50 border border-amber-300 rounded p-3">
            <span className="text-amber-500 mt-0.5">⚠</span>
            <div className="flex-1">
              <p className="text-sm text-amber-600 font-medium">
                {avgMissing.toFixed(1)}% average missing data — analysis blocked
              </p>
              <p className="text-xs text-gray-500 mt-1">
```

Backend warnings:
```tsx
            <div key={i} className="flex gap-2 bg-amber-50 border border-amber-300 rounded p-2 text-xs text-amber-600">
```

Ticker cards:
```tsx
            <div key={ticker} className="bg-white rounded border border-gray-200 p-3 group">
              <div className="flex items-baseline gap-2 mb-1">
                <div className="text-xs font-mono text-gray-500">{ticker}</div>
                {TICKER_DESCRIPTIONS[ticker] && (
                  <div className="text-[10px] text-gray-300 group-hover:text-gray-500 transition-colors truncate">
```

Stats:
```tsx
                <div className="flex gap-3 mt-1 text-[10px] text-gray-400 font-mono">
```

Error state:
```tsx
        <p className="text-red-500 text-sm">{fetchError}</p>
```

Loading state:
```tsx
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
```

- [ ] **Step 6: Update UploadSection**

```tsx
    <div className="border border-gray-200 rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-400 hover:text-gray-700 transition-colors"
      >
        <span>Upload additional data</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-gray-200 p-4">
```

- [ ] **Step 7: Commit**

```bash
git add "frontend/app/sessions/[id]/data/page.tsx"
git commit -m "feat: light theme — data page"
```

---

### Task 11: Tab components

**Files:**
- Modify: `frontend/components/tabs/TabPlaceholder.tsx`
- Modify: `frontend/components/tabs/OverviewTab.tsx`
- Modify: `frontend/components/tabs/SummaryTab.tsx`
- Modify: `frontend/components/tabs/BacktestTab.tsx`
- Modify: `frontend/components/tabs/FeaturesTab.tsx`
- Modify: `frontend/components/tabs/DriftTab.tsx`

- [ ] **Step 1: Rewrite TabPlaceholder.tsx**

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
        <div className="text-[28px] text-gray-200 mb-3">{icon}</div>
        <div className="text-xs text-gray-500 font-mono font-semibold mb-1.5">
          {title}
        </div>
        <div className="text-[10px] text-gray-400 font-mono leading-relaxed">
          {reason}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update OverviewTab.tsx**

`StatTile` component:
```tsx
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
    <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${accent ?? "text-gray-700"}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-gray-400 font-mono">{sub}</div>}
    </div>
  );
}
```

`DistBar` component:
```tsx
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
      <div className="w-28 text-right text-gray-500 truncate">{label}</div>
      <div className="flex-1 bg-gray-100 rounded h-2 overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-8 text-gray-400 text-right">{pct.toFixed(0)}%</div>
    </div>
  );
}
```

In `OverviewTab` JSX, replace the two distribution card wrappers:
```tsx
        <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-2">
```

Replace `StatTile` accent props:
- `accent="text-violet-400"` (Regime) → `accent="text-teal-600"`
- `accent="text-violet-300"` (Top Signal) → `accent="text-teal-600"`

Replace `bg-violet-600` in DistBar color for range_bound/default regime → `bg-teal-600`.

- [ ] **Step 3: Rewrite SummaryTab.tsx**

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
      <div className="bg-white border border-gray-200 rounded p-5">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-4">
          Agent Narrative
        </div>
        <p
          className="text-sm text-gray-700 leading-7"
          dangerouslySetInnerHTML={{ __html: renderSummary(summary) }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update BacktestTab.tsx**

`MetricTile`:
```tsx
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
    <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-2xl font-mono font-bold ${accent ?? "text-gray-700"}`}>
        {value}
      </div>
    </div>
  );
}
```

Chart wrapper:
```tsx
      <div className="bg-white border border-gray-200 rounded p-4 flex-1 min-h-[180px]">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-3">
```

Recharts props:
```tsx
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: "#6b7280", fontFamily: "monospace" }}
            />
            <YAxis tick={{ fontSize: 10, fill: "#6b7280", fontFamily: "monospace" }} />
            <Tooltip
              contentStyle={{
                background: "#ffffff",
                border: "1px solid #e5e7eb",
                borderRadius: 4,
                fontSize: 11,
                fontFamily: "monospace",
              }}
            />
```

Bar colors:
```tsx
            <Bar dataKey="Strategy" fill="#0d9488" radius={[2, 2, 0, 0]} />
            <Bar dataKey="Benchmark" fill="#9ca3af" radius={[2, 2, 0, 0]} />
```

Footer note:
```tsx
        <div className="text-[10px] text-gray-400 font-mono mt-2">
```

`MetricTile` accent for strategy: `text-violet-400` → `text-teal-600`

- [ ] **Step 5: Update FeaturesTab.tsx**

Card wrapper:
```tsx
      <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-2 flex-1">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-2">
```

Feature rows:
```tsx
              <div className="w-32 text-right text-xs text-gray-500 font-mono truncate">
```
```tsx
              <div className="flex-1 bg-gray-100 rounded h-3 overflow-hidden">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(f.importance / max) * 100}%`,
                    background: `#0d9488`,
                    opacity: 1 - i * 0.06,
                  }}
                />
              </div>
              <div className="w-12 text-right text-xs text-gray-400 font-mono">
```

Footer:
```tsx
        <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
```

- [ ] **Step 6: Update DriftTab.tsx**

`StatTile` (same as BacktestTab's `MetricTile` but smaller):
```tsx
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
    <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${accent ?? "text-gray-700"}`}>
        {value}
      </div>
    </div>
  );
}
```

KS table wrapper:
```tsx
      <div className="bg-white border border-gray-200 rounded overflow-hidden">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest p-3 border-b border-gray-200">
```

KS rows:
```tsx
        <div className="divide-y divide-gray-100">
```
```tsx
                  <div className="flex-1 text-gray-700 truncate">{feature}</div>
                  <div className="text-gray-400 w-12 text-right">
                    {statistic.toFixed(3)}
                  </div>
                  <div className="text-gray-400 w-12 text-right">
                    p={p_value.toFixed(3)}
                  </div>
                  <div
                    className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                      isDrifted
                        ? "bg-amber-50 text-amber-600"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
```

Interpretation card:
```tsx
      <div className="bg-white border border-gray-200 rounded p-3">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-2">
          Interpretation
        </div>
        <p className="text-xs text-gray-600 leading-relaxed">
```

- [ ] **Step 7: Commit all tabs**

```bash
git add frontend/components/tabs/
git commit -m "feat: light theme — tab components"
```

---

### Task 12: Verify and final commit

- [ ] **Step 1: Run type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors. If errors appear, fix them before continuing.

- [ ] **Step 2: Start dev server and verify visually**

```bash
cd frontend && npm run dev
```

Check these pages at http://localhost:3000:
1. Home page (`/`) — white background, teal "+ New Analysis" button, light table
2. Session detail (`/sessions/<id>/activity`) — white sidebar, light stage strip, teal active pill, white chat bubbles
3. Data page — white cards, teal sparkline, light table
4. Config page — white background, teal active tags
5. NewAnalysisModal — white modal with teal submit button

Look for any remaining dark backgrounds (`#0d1117`, `#111827`, etc.) that were missed.

- [ ] **Step 3: Run lint**

```bash
cd frontend && npm run lint
```

Fix any lint errors.

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -p
git commit -m "fix: light theme — cleanup remaining dark classes"
```
