# Unified Activity Chat Design

**Date:** 2026-06-05
**Branch:** feat/agent-data-pipeline

## Problem

The chat widget (currently a floating bubble) is visually disconnected from the agent's thinking and tool-call activity shown in the Activity tab. Users mentally track two separate streams — the activity feed and the chat — when they are really one coherent timeline. The floating widget also blocks content and has no natural home when the user navigates to Data or Results.

## Goal

Merge chat into the Activity tab so the agent's messages, user replies, thinking, and tool calls all flow in a single chronological stream. Replace the floating widget with a contextual navigation banner that guides users back to Activity when action is needed.

---

## Design

### 1. Unified Activity Stream

The Activity tab (`activity/page.tsx`) becomes the single place for everything that happens during a session.

**Stream composition** — all items sorted by `created_at`:
- **Stage cards** (existing) — collapsable, contain thoughts and tool-call rows
- **Agent chat messages** — rendered as a left-aligned dark bubble, same styling as the current `ChatBubble` component (role=assistant)
- **User chat messages** — rendered as a right-aligned blue bubble (role=user)

`buildGroups()` is extended to accept `conversation: ChatMessage[]`. Conversation messages are interleaved into the flat event list by timestamp before grouping, then attached to whichever `StageGroup` was active when they were sent (same `created_at` comparison). Within a group, chat messages render after `fetchRows` and `thoughts` but before the `completionEvent`.

`ChatMessage` already has `created_at` (ISO string), so no schema changes needed.

**Input bar** — a single `<input>` + send button pinned to the bottom of the Activity tab scroll container. Visible only when `stage === "user_review"`. Disabled (opacity-40) when `status !== "waiting"`. On send: calls `api.sendChat()`, then refreshes the session via `api.getSession()` (same as current `onSent` callback). Entering a message while `status === "running"` shows a "Agent is thinking…" placeholder instead of the input.

### 2. FloatingChat Removed

`FloatingChat` component and its render in `layout.tsx` are deleted. The `{stage === "user_review" && <FloatingChat .../>}` block is removed entirely.

### 3. ReviewBanner

A slim one-line banner rendered below the tab bar in `layout.tsx`, visible only when:
- `stage === "user_review"`, AND
- the current pathname is NOT the Activity tab

Banner copy is state-driven:

| Condition (checked in order) | Text |
|---|---|
| `status === "running"` | `· Agent is thinking… view in Activity →` |
| last conversation message has `role === "assistant"` | `· Agent replied — go to Activity to respond →` |
| default | `· Satisfied with the data? Go to Activity to proceed →` |

The `→` is a `<Link href="/sessions/{id}/activity">` that navigates directly. The banner has a left blue pulsing dot. No close/dismiss button — it disappears automatically when the user navigates to Activity.

---

## Component Map

| File | Change |
|---|---|
| `layout.tsx` | Delete `FloatingChat`; add `ReviewBanner` below tab bar |
| `activity/page.tsx` | Extend `buildGroups()` to accept + interleave `conversation`; add `ChatMessageItem` component; add input bar at bottom |

No backend changes. No store changes. `ChatMessage.created_at` is already present.

---

## Out of Scope

- Resize / fullscreen chat panel (deferred)
- Chat available outside `user_review` stage
- Marking messages as "read" / unread count badge
