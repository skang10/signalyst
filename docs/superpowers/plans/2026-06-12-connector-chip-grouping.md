# Connector Chip Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `ConnectorEditor.tsx` so each connector shows its individual sources as toggleable chips — Yahoo Finance shows one chip per ticker (editable), FRED/EIA/GPR Index each show a single labeled chip.

**Architecture:** Single-component rewrite. Each connector renders as a "group" (header + chip row). A shared `Chip` subcomponent renders active/inactive state. Yahoo Finance chips come from `params.tickers` (add/remove mutates that array, removing the connector entry entirely when empty). Other connectors get one chip from a static `SOURCE_LABELS` map, toggling `pending_sources` membership exactly as the old row-click did.

**Tech Stack:** Next.js 15, React, TypeScript, Tailwind CSS, Vitest + Testing Library.

---

## Background

See `docs/superpowers/specs/2026-06-12-connector-chip-grouping-design.md` for the full design rationale. No backend changes. No new test infrastructure — the project already has Vitest + Testing Library set up (see `frontend/components/__tests__/GateMessage.test.tsx` for the pattern).

---

## Task 1: Write failing tests for the new ConnectorEditor

**Files:**
- Create: `frontend/components/__tests__/ConnectorEditor.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ConnectorEditor } from "../ConnectorEditor";
import type { ConnectorOut, PendingSource } from "@/lib/api";

const connectors: ConnectorOut[] = [
  {
    id: "yfinance",
    name: "Yahoo Finance",
    description: "Daily price series from Yahoo Finance. Supports equities, ETFs, and futures.",
    type: "yfinance",
    available: true,
  },
  {
    id: "fred",
    name: "FRED",
    description: "Macro time series from the St. Louis Fed FRED database.",
    type: "fred",
    available: true,
  },
  {
    id: "eia",
    name: "EIA",
    description: "Weekly US crude oil inventory change from the EIA.",
    type: "eia",
    available: true,
  },
  {
    id: "gpr",
    name: "GPR Index",
    description: "Daily Geopolitical Risk Index from the Federal Reserve.",
    type: "gpr",
    available: true,
  },
];

const baseValue: PendingSource[] = [
  { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
  { connector_id: "fred" },
  { connector_id: "eia" },
];

describe("ConnectorEditor", () => {
  it("renders one chip per yfinance ticker and a single labeled chip for other connectors", () => {
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={() => {}} />);

    expect(screen.getByText("CL=F")).toBeTruthy();
    expect(screen.getByText("BZ=F")).toBeTruthy();
    expect(screen.getByText("DX-Y.NYB")).toBeTruthy();
    expect(screen.getByText("INDPRO")).toBeTruthy(); // fred, active
    expect(screen.getByText("Inventory")).toBeTruthy(); // eia, active
    expect(screen.getByText("GPR")).toBeTruthy(); // gpr, inactive (not in baseValue)
  });

  it("removes a ticker from params.tickers when its chip is clicked", () => {
    const onChange = vi.fn();
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={onChange} />);

    fireEvent.click(screen.getByText("BZ=F"));

    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "yfinance", params: { tickers: ["CL=F", "DX-Y.NYB"] } },
      { connector_id: "fred" },
      { connector_id: "eia" },
    ]);
  });

  it("removes the yfinance entry entirely when its last ticker is removed", () => {
    const onChange = vi.fn();
    const value: PendingSource[] = [
      { connector_id: "yfinance", params: { tickers: ["CL=F"] } },
      { connector_id: "fred" },
    ];
    render(<ConnectorEditor available={connectors} value={value} onChange={onChange} />);

    fireEvent.click(screen.getByText("CL=F"));

    expect(onChange).toHaveBeenCalledWith([{ connector_id: "fred" }]);
  });

  it("adds a ticker via the + Add input, creating the yfinance entry if missing", () => {
    const onChange = vi.fn();
    const value: PendingSource[] = [{ connector_id: "fred" }];
    render(<ConnectorEditor available={connectors} value={value} onChange={onChange} />);

    fireEvent.click(screen.getByText("+ Add"));
    const input = screen.getByPlaceholderText("e.g. XLE");
    fireEvent.change(input, { target: { value: "XLE" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "fred" },
      { connector_id: "yfinance", params: { tickers: ["XLE"] } },
    ]);
  });

  it("toggles a single-source connector in and out of pending_sources via its chip", () => {
    const onChange = vi.fn();
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={onChange} />);

    fireEvent.click(screen.getByText("GPR")); // inactive -> active
    expect(onChange).toHaveBeenCalledWith([...baseValue, { connector_id: "gpr" }]);

    fireEvent.click(screen.getByText("INDPRO")); // fred active -> inactive
    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
      { connector_id: "eia" },
    ]);
  });

  it("renders chips read-only with no + Add button and ignores clicks", () => {
    const onChange = vi.fn();
    render(
      <ConnectorEditor available={connectors} value={baseValue} onChange={onChange} readOnly />,
    );

    expect(screen.queryByText("+ Add")).toBeNull();

    fireEvent.click(screen.getByText("BZ=F"));
    fireEvent.click(screen.getByText("INDPRO"));

    expect(onChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd frontend && npx vitest run components/__tests__/ConnectorEditor.test.tsx`
Expected: FAIL — the current component renders a single dot/checkbox per connector, an inline `Tickers:` text input for yfinance, and no chips, so none of the `getByText`/`getByPlaceholderText` queries above will find their targets.

---

## Task 2: Rewrite ConnectorEditor.tsx

**Files:**
- Modify: `frontend/components/ConnectorEditor.tsx` (full rewrite)

- [ ] **Step 1: Replace the file contents**

```tsx
"use client";

import { useState } from "react";
import type { ConnectorOut, PendingSource } from "@/lib/api";

type Props = {
  available: ConnectorOut[];
  value: PendingSource[];
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
};

// Static display label for connectors that contribute a single source.
// Connectors not listed here fall back to their own `name`.
const SOURCE_LABELS: Record<string, string> = {
  fred: "INDPRO",
  eia: "Inventory",
  gpr: "GPR",
};

function Checkmark() {
  return (
    <svg
      className="w-3 h-3"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={[
        "flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-mono font-semibold transition-colors",
        active
          ? "bg-teal-50 border-teal-200 text-teal-700"
          : "bg-gray-50 border-gray-200 text-gray-400",
        onClick ? "cursor-pointer" : "cursor-default",
      ].join(" ")}
    >
      <span
        className={[
          "w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0",
          active ? "bg-teal-600 border-teal-600 text-white" : "border-gray-300",
        ].join(" ")}
      >
        {active && <Checkmark />}
      </span>
      {label}
    </button>
  );
}

export function ConnectorEditor({ available, value, onChange, readOnly }: Props) {
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [addValue, setAddValue] = useState("");
  const activeIds = new Set(value.map((s) => s.connector_id));

  function toggleConnector(connector: ConnectorOut) {
    if (readOnly) return;
    if (activeIds.has(connector.id)) {
      onChange(value.filter((s) => s.connector_id !== connector.id));
    } else {
      onChange([...value, { connector_id: connector.id }]);
    }
  }

  function removeTicker(connectorId: string, ticker: string) {
    if (readOnly) return;
    const source = value.find((s) => s.connector_id === connectorId);
    const tickers = (source?.params?.tickers as string[] | undefined) ?? [];
    const next = tickers.filter((t) => t !== ticker);
    if (next.length === 0) {
      onChange(value.filter((s) => s.connector_id !== connectorId));
    } else {
      onChange(
        value.map((s) =>
          s.connector_id === connectorId ? { ...s, params: { ...s.params, tickers: next } } : s,
        ),
      );
    }
  }

  function addTicker(connectorId: string, ticker: string) {
    if (readOnly) return;
    const trimmed = ticker.trim();
    if (!trimmed) return;
    const source = value.find((s) => s.connector_id === connectorId);
    if (!source) {
      onChange([...value, { connector_id: connectorId, params: { tickers: [trimmed] } }]);
      return;
    }
    const tickers = (source.params?.tickers as string[] | undefined) ?? [];
    onChange(
      value.map((s) =>
        s.connector_id === connectorId
          ? { ...s, params: { ...s.params, tickers: [...tickers, trimmed] } }
          : s,
      ),
    );
  }

  function confirmAdd(connectorId: string) {
    addTicker(connectorId, addValue);
    setAddingFor(null);
    setAddValue("");
  }

  if (available.length === 0) {
    return (
      <div className="border border-gray-200 rounded-lg px-3 py-4 text-xs text-gray-400 text-center">
        No connectors configured.
      </div>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="text-[10px] text-gray-400 px-3 py-2 border-b border-gray-100 bg-gray-50 font-mono uppercase tracking-widest">
        Click a chip to toggle · active sources used on next data run
      </div>
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        const isYfinance = connector.id === "yfinance";
        const tickers = (source?.params?.tickers as string[] | undefined) ?? [];

        return (
          <div key={connector.id} className="px-3 py-2.5 border-b border-gray-100 last:border-0">
            <div className="flex items-baseline gap-2">
              <span
                className={`text-sm font-medium ${isActive ? "text-teal-700" : "text-gray-500"}`}
              >
                {connector.name}
              </span>
              <span className="text-xs text-gray-400 truncate">{connector.description}</span>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {isYfinance ? (
                <>
                  {tickers.map((ticker) => (
                    <Chip
                      key={ticker}
                      label={ticker}
                      active
                      onClick={readOnly ? undefined : () => removeTicker(connector.id, ticker)}
                    />
                  ))}
                  {!readOnly &&
                    (addingFor === connector.id ? (
                      <input
                        autoFocus
                        value={addValue}
                        onChange={(e) => setAddValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") confirmAdd(connector.id);
                          if (e.key === "Escape") {
                            setAddValue("");
                            setAddingFor(null);
                          }
                        }}
                        onBlur={() => confirmAdd(connector.id)}
                        placeholder="e.g. XLE"
                        className="text-xs font-mono border border-teal-200 rounded px-2 py-1 outline-none focus:border-teal-400 w-24"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setAddingFor(connector.id);
                          setAddValue("");
                        }}
                        className="px-2 py-1 rounded-md border border-dashed border-gray-300 text-xs text-gray-400 hover:border-teal-300 hover:text-teal-600"
                      >
                        + Add
                      </button>
                    ))}
                </>
              ) : (
                <Chip
                  label={SOURCE_LABELS[connector.id] ?? connector.name}
                  active={isActive}
                  onClick={readOnly ? undefined : () => toggleConnector(connector)}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Run the tests to confirm they pass**

Run: `cd frontend && npx vitest run components/__tests__/ConnectorEditor.test.tsx`
Expected: PASS — all 6 tests green.

---

## Task 3: Type-check, lint, and commit

- [ ] **Step 1: Run type-check**

Run: `cd frontend && npm run type-check`
Expected: no errors.

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: no errors/warnings.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: all tests pass, including the new `ConnectorEditor.test.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ConnectorEditor.tsx frontend/components/__tests__/ConnectorEditor.test.tsx
git commit -m "feat: show connector sources as individual toggleable chips"
```
