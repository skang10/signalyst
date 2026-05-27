# Agent Progress Stream Design

## Goal

Replace the left-panel raw tool stream with a hybrid progress timeline and evidence notebook. The panel should answer two questions while an analysis is running:

1. What phase is the agent in?
2. What did each phase learn?

Raw backend events should remain available for debugging, but they should not be the primary reading experience.

## Current Problem

The backend already emits useful structured events, including `phase`, `tabpfn_estimate`, `tabpfn_progress`, `tool_call`, `tool_result`, `thought`, and `done`.

The frontend currently renders only a simple chronological list of raw messages, so the stream is dominated by labels like `tool_call run_tabpfn` and `tool_result fetch_data`. This is technically transparent but not meaningful to a product user.

## Product Direction

Use a hybrid **Agent Progress** panel:

- Timeline structure for agent phases.
- Notebook-style evidence inside completed phases.
- Live progress for long-running model work, especially TabPFN calls.
- Collapsed raw event disclosure at the bottom for debugging.

The raw event disclosure should be collapsed by default and labeled with the event count, for example `Raw events · 14 messages`.

## Phase Model

The frontend should group stream events into these user-facing phases:

| Phase | Purpose |
| --- | --- |
| `Preparing data` | Market, macro, and geopolitical data collection |
| `Engineering features` | Feature construction from source signals |
| `Checking drift` | Feature drift and reliability checks |
| `Predicting regime` | TabPFN regime classification |
| `Predicting direction` | TabPFN WTI direction prediction |
| `Evaluating features` | Lightweight SHAP / feature importance analysis |
| `Backtesting` | Historical validation when enabled |
| `Explaining drivers` | Final narrative synthesis |
| `Final summary` | Completed run summary |

Each phase has a status:

- `waiting`
- `running`
- `done`
- `failed`
- `canceled`

## Event Mapping

The frontend should transform raw WebSocket messages into phase state:

| Event | UI behavior |
| --- | --- |
| `phase` | Mark the mapped phase as `running`; mark prior running phase as `done` unless already terminal |
| `tabpfn_estimate` | Show total expected TabPFN calls near the panel header |
| `tabpfn_progress` | Update model-call progress and attach it to the active prediction/evaluation/backtest phase |
| `tool_call` | Store in raw events; optionally set phase metadata from tool input |
| `tool_result` | Store in raw events and extract concise evidence for the mapped phase |
| `thought` | Store as narrative note for the current phase if short; otherwise raw event only |
| `done` | Mark final summary as `done`, show summary text, and finish any running phase |

The existing raw message history cap can remain, but phase state should be derived from retained messages and should not show duplicate `tool_call` / `tool_result` rows in the primary UI.

## Evidence Extraction

Evidence should be concise and phase-specific. It should avoid dumping JSON.

Examples:

- Data phase: tickers loaded, date range, source count.
- Drift phase: drift label and PSI score.
- Regime phase: predicted regime and confidence.
- Direction phase: predicted direction and confidence.
- Feature evaluation phase: top features from SHAP or fallback importance.
- Backtest phase: window count and headline accuracy metrics.
- Explanation phase: key caveats and confidence framing.

If a tool result shape is missing or unexpected, the UI should still mark the phase as completed and show a neutral note like `Completed; no compact evidence available`.

## Layout

The panel header should show:

- `Agent Progress`
- analysis mode when available, for example `Quick analysis`
- compact model progress when available, for example `TabPFN 2 / 2`

The body should render a vertical timeline. Each phase row should include:

- status indicator
- phase title
- short description
- evidence chips or a compact evidence table
- progress bar only when that phase has measurable progress

The bottom should include a collapsed raw event disclosure:

`Raw events · N messages`

When expanded, render compact monospace lines for debugging:

- `phase predicting_regime`
- `tool_call run_tabpfn {"task":"regime"}`
- `tabpfn_progress 1/2`
- `tool_result run_tabpfn`

## Backend Changes

Prefer frontend-only implementation first. The backend already publishes the key events needed for this design.

Backend changes are only needed if the frontend cannot reliably infer evidence from current `tool_result` shapes. In that case, add small optional fields to existing events rather than introducing a new streaming protocol.

## Error Handling

- If WebSocket disconnects during a run, keep the current phase timeline visible and show a small connection warning.
- If the run is canceled, mark the active phase as `canceled` and stop advancing.
- If the run fails, mark the active phase as `failed` and keep raw events available for diagnosis.
- Unknown event types should be retained in raw events and ignored by the primary timeline.

## Testing

Add focused frontend tests for:

- `phase` events advancing timeline state.
- `tabpfn_estimate` and `tabpfn_progress` rendering model-call progress.
- `tool_result` evidence extraction for regime, direction, drift, and feature importance.
- collapsed raw events disclosure and expanded raw-event rendering.
- disconnected, failed, and canceled states.

Keep backend tests unchanged unless backend event payloads need to change.
