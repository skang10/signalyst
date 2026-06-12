# Connector Chip Grouping Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Data Sources editor show individual signals ("sources"), not just connectors — e.g. Yahoo Finance contributes 3 separate tickers, while FRED/EIA/GPR Index each contribute 1.

**Architecture:** Rewrite `ConnectorEditor.tsx` to render each connector as a "group": a header (name + description) followed by a row of chips, one per underlying source. Yahoo Finance's chips are its `params.tickers` (editable — add/remove ticker chips). All other connectors show a single chip with a static display label, toggling connector inclusion in `pending_sources` (same as today's row click).

**Tech Stack:** Next.js 15, React, Tailwind CSS. No backend changes — `pending_sources` / `params.tickers` shape is unchanged.

---

## Background

The current `ConnectorEditor` shows one row per connector (Yahoo Finance, FRED, EIA, GPR Index, custom connectors), each toggleable via a checkbox. Yahoo Finance is special-cased with an inline text input for its `params.tickers` (a comma-separated list, e.g. `CL=F, BZ=F, DX-Y.NYB`).

This hides the fact that Yahoo Finance actually contributes 3 separate time series while FRED/EIA/GPR Index contribute 1 each — 6 "sources" total from 4 connectors. Users should be able to see and toggle these 6 sources directly, and add/remove individual Yahoo Finance tickers without editing a raw comma-separated string.

---

## Layout

Each connector renders as a "group":

```
[name]  [description]
[chip] [chip] [chip] [+ Add]
```

- Group header styling matches the current row header (name in teal when active, gray description text).
- Chips sit in a flex-wrap row below the header.
- Active chip: teal background/border/text, filled teal checkmark icon.
- Inactive chip: gray background/border/text, empty checkbox outline.

---

## Chip semantics

### Yahoo Finance (`connector.id === "yfinance"`)

- One chip per entry in `params.tickers`, label = the ticker symbol (e.g. `CL=F`).
- All ticker chips render as active (there is no "available but unselected ticker" catalog).
- Clicking a ticker chip **removes** that ticker from `params.tickers`.
  - If this empties `params.tickers`, the yfinance entry is removed from `pending_sources` entirely. The group still renders (header + "+ Add" chip), just with zero ticker chips.
- A dashed `+ Add` chip, when clicked, reveals a small inline text input. Pressing Enter (or a confirm action) appends the trimmed, non-empty value to `params.tickers`, creating the yfinance `pending_sources` entry if it doesn't exist. Input clears and hides after a successful add.
- Whitespace-only or empty input on add is a no-op (input just closes).

### All other connectors (FRED, EIA, GPR Index, custom connectors)

- Exactly one chip per connector.
- Chip label comes from a static frontend lookup table keyed by `connector.id`:
  ```ts
  const SOURCE_LABELS: Record<string, string> = {
    fred: "INDPRO",
    eia: "Inventory",
    gpr: "GPR",
  };
  ```
  Fallback for connectors not in the table: use `connector.name` (e.g. "My Connector" → chip labeled "My Connector").
- Clicking the chip toggles the connector's membership in `pending_sources` (identical to today's row-click behavior — add `{ connector_id: connector.id }` / remove the matching entry).
- Chip active state = `activeIds.has(connector.id)`, same as the group header's active state.

---

## Read-only mode

`readOnly` prop behaves as today: chips render with their current active/inactive styling but `onClick` handlers are no-ops. The "+ Add" chip is hidden entirely in read-only mode.

---

## Out of scope

- No backend/API changes.
- No catalog of "available but unselected" Yahoo Finance tickers — removed tickers must be re-typed via "+ Add" to restore.
- No validation of ticker symbols beyond non-empty/trim.
- FRED's `params.series_ids` remains unused/uneditable in the UI (unchanged from current behavior).

---

## Testing

- Update/extend any existing `ConnectorEditor` tests (if present) to cover:
  - Rendering chips per connector (yfinance multi-chip, others single-chip).
  - Removing a yfinance ticker chip updates `params.tickers` / removes the entry when empty.
  - "+ Add" appends a ticker and creates the entry if missing.
  - Clicking a single-source connector chip toggles `pending_sources` membership.
- `npm run type-check` and `npm run lint` must pass.
