"use client";

import { useState } from "react";
import { useSessionStore } from "@/lib/store";
import type { ActivityEvent } from "@/lib/api";

// --- Types ---

type FetchRow = {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown> | null;
  callTime: string;
  resultTime: string | null;
};

type ThoughtEntry = {
  id: string;
  content: string;
  time: string;
};

type StageGroup = {
  stage: string;
  startTime: string;
  status: "done" | "active" | "failed";
  thoughts: ThoughtEntry[];
  fetchRows: FetchRow[];
  completionEvent: Record<string, unknown> | null;
  errorEvent: Record<string, unknown> | null;
};

// --- Labels ---

const STAGE_LABELS: Record<string, string> = {
  configuring: "Source Discovery",
  data_gathering: "Data Gathering",
  user_review: "Review",
  featurizing: "Featurizing",
  analyzing: "Analyzing",
  explaining: "Explaining",
  follow_up: "Follow-Up",
};

const TOOL_DISPLAY: Record<string, (i: Record<string, unknown>) => string> = {
  fetch_yfinance: (i) => `yfinance · ${(i.tickers as string[] | undefined)?.join(", ") ?? ""}`,
  fetch_fred: (i) => `FRED · ${(i.series_ids as string[] | undefined)?.join(", ") ?? ""}`,
  fetch_eia: () => "EIA · crude inventory",
  fetch_gpr: () => "GPR · geopolitical risk index",
  fetch_custom_connector: (i) => `connector · ${i.connector_id ?? ""}`,
  list_available_connectors: () => "Listed connectors",
  approve_sources: () => "Approved sources",
  save_connector_spec: (i) => `Saved connector · ${i.id ?? ""}`,
  http_get: (i) => `GET · ${(i.url as string | undefined)?.replace(/^https?:\/\//, "") ?? ""}`,
  http_post: (i) => `POST · ${(i.url as string | undefined)?.replace(/^https?:\/\//, "") ?? ""}`,
};

function toolDisplay(tool: string, input: Record<string, unknown>): string {
  return TOOL_DISPLAY[tool]?.(input) ?? tool.replace(/_/g, " ");
}

// --- Group builder ---

type MutableGroup = Omit<StageGroup, "status"> & {
  pendingQueues: Map<string, FetchRow[]>;
};

function newGroup(stage: string, startTime: string): MutableGroup {
  return {
    stage,
    startTime,
    thoughts: [],
    fetchRows: [],
    pendingQueues: new Map(),
    completionEvent: null,
    errorEvent: null,
  };
}

function flushPending(g: MutableGroup) {
  g.pendingQueues.forEach((queue) => g.fetchRows.push(...queue));
  g.pendingQueues.clear();
}

function buildGroups(
  activityEvents: ActivityEvent[],
  wsMessages: Record<string, unknown>[],
  currentStage: string | null,
  currentStatus: string | null,
): StageGroup[] {
  const ts = (iso: string | undefined) => (iso ? new Date(iso).getTime() || 0 : 0);

  const merged = [
    ...activityEvents.map((e) => ({ t: ts(e.created_at), ev: e as Record<string, unknown> })),
    ...wsMessages
      .filter((m) => ["thought", "tool_call", "tool_result"].includes(m.type as string))
      .map((m) => ({ t: ts(m.created_at as string | undefined), ev: m })),
  ].sort((a, b) => a.t - b.t);

  let cur = newGroup("configuring", "");
  const completed: MutableGroup[] = [];
  let thoughtIdx = 0;
  let fetchIdx = 0;

  for (const { ev } of merged) {
    const type = ev.type as string;

    if (type === "stage_transition") {
      flushPending(cur);
      completed.push(cur);
      cur = newGroup((ev.to as string) ?? "", (ev.created_at as string) ?? "");
    } else if (type === "artifact_ready" || type === "cache_hit") {
      cur.completionEvent = ev;
    } else if (type === "error") {
      cur.errorEvent = ev;
    } else if (type === "thought") {
      cur.thoughts.push({
        id: `th-${thoughtIdx++}`,
        content: (ev.content as string) ?? "",
        time: (ev.created_at as string) ?? "",
      });
    } else if (type === "tool_call") {
      const tool = ev.tool as string;
      if (tool === "complete") continue;
      const row: FetchRow = {
        id: `fr-${fetchIdx++}`,
        tool,
        input: (ev.input as Record<string, unknown>) ?? {},
        result: null,
        callTime: (ev.created_at as string) ?? "",
        resultTime: null,
      };
      const q = cur.pendingQueues.get(tool) ?? [];
      q.push(row);
      cur.pendingQueues.set(tool, q);
    } else if (type === "tool_result") {
      const tool = ev.tool as string;
      const q = cur.pendingQueues.get(tool);
      if (q?.length) {
        const row = q.shift()!;
        row.result = (ev.output as Record<string, unknown>) ?? {};
        row.resultTime = (ev.created_at as string) ?? "";
        cur.fetchRows.push(row);
        if (q.length === 0) cur.pendingQueues.delete(tool);
      }
    }
  }

  flushPending(cur);
  const all = [...completed, cur];

  return all.map((g, idx): StageGroup => {
    const isLast = idx === all.length - 1;
    let status: "done" | "active" | "failed" = "done";
    if (isLast) {
      if (g.errorEvent || currentStatus === "failed" || currentStatus === "canceled") {
        status = "failed";
      } else if (currentStatus === "running") {
        status = "active";
      } else {
        status = "done";
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { pendingQueues: _, ...rest } = g;
    return { ...rest, status };
  });
}

// --- Fetch row ---

function FetchRowItem({ row }: { row: FetchRow }) {
  const [open, setOpen] = useState(false);
  const label = toolDisplay(row.tool, row.input);
  const ready = row.result !== null;

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-[#111827] transition-colors group"
      >
        <span className="text-[#374151] text-xs w-3 flex-shrink-0">{open ? "▾" : "▸"}</span>
        <span className="text-sm text-[#d1d5db] flex-1 truncate">{label}</span>
        <span className={`text-xs flex-shrink-0 ${ready ? "text-[#22c55e]" : "text-[#3b82f6] animate-pulse"}`}>
          {ready ? "→ ready" : "fetching…"}
        </span>
      </button>
      {open && (
        <div className="mx-4 mb-1 ml-9 border-l border-[#1f2937] pl-3 py-1 space-y-0.5">
          <div className="text-xs font-mono text-[#6b7280]">
            <span className="text-[#4b5563]">input </span>
            <span className="text-[#9ca3af] break-all">
              {JSON.stringify(row.input)}
            </span>
          </div>
          {row.result && (
            <div className="text-xs font-mono text-[#6b7280]">
              <span className="text-[#4b5563]">output </span>
              <span className="text-[#9ca3af] break-all">
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

// --- Thought row ---

function ThoughtRowItem({ thought }: { thought: ThoughtEntry }) {
  const [open, setOpen] = useState(false);
  const preview =
    thought.content.length > 120 ? thought.content.slice(0, 120) + "…" : thought.content;

  return (
    <button
      onClick={() => setOpen((o) => !o)}
      className="flex items-start gap-2 w-full text-left px-4 py-1 hover:bg-[#111827] transition-colors"
    >
      <span className="text-[#374151] text-xs mt-0.5 w-3 flex-shrink-0">💭</span>
      <span className="text-xs text-[#4b5563] italic leading-snug text-left">
        {open ? thought.content : preview}
      </span>
    </button>
  );
}

// --- Completion summary ---

function CompletionSummary({ event }: { event: Record<string, unknown> }) {
  if (event.type === "artifact_ready") {
    const kind = event.kind as string;
    if (kind === "data") {
      const rows = event.rows as number | undefined;
      const tickers = (event.tickers as string[] | undefined) ?? [];
      return (
        <div className="px-4 py-1.5 text-xs text-[#22c55e]">
          ✓ {rows} rows · {tickers.length} signal{tickers.length !== 1 ? "s" : ""}
          {tickers.length > 0 && (
            <span className="text-[#166534] ml-1">({tickers.slice(0, 4).join(", ")}{tickers.length > 4 ? ` +${tickers.length - 4}` : ""})</span>
          )}
        </div>
      );
    }
    if (kind === "features") {
      return (
        <div className="px-4 py-1.5 text-xs text-[#22c55e]">
          ✓ {event.n_features as number} features · {event.n_rows as number} rows
        </div>
      );
    }
    if (kind === "analysis") {
      const regime = event.regime as string | undefined;
      return (
        <div className="px-4 py-1.5 text-xs text-[#22c55e]">
          ✓ Analysis complete{regime ? ` · ${regime}` : ""}
        </div>
      );
    }
  }
  if (event.type === "cache_hit") {
    return (
      <div className="px-4 py-1.5 text-xs text-[#a78bfa]">⚡ cache hit — reused prior result</div>
    );
  }
  return null;
}

// --- Stage card ---

function StageCard({ group, defaultOpen }: { group: StageGroup; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  const hasContent =
    group.fetchRows.length > 0 ||
    group.thoughts.length > 0 ||
    group.completionEvent !== null ||
    group.errorEvent !== null;

  const ts = group.startTime ? new Date(group.startTime).toLocaleTimeString() : "";

  const dot =
    group.status === "active" ? (
      <span className="w-2 h-2 rounded-full bg-[#3b82f6] animate-pulse flex-shrink-0" />
    ) : group.status === "failed" ? (
      <span className="w-2 h-2 rounded-full bg-[#ef4444] flex-shrink-0" />
    ) : (
      <span className="w-2 h-2 rounded-full bg-[#22c55e] flex-shrink-0" />
    );

  return (
    <div className="border border-[#1f2937] rounded-lg overflow-hidden">
      <button
        onClick={() => hasContent && setOpen((o) => !o)}
        className={`flex items-center gap-3 w-full px-4 py-2.5 bg-[#111827] text-left transition-colors ${
          hasContent ? "hover:bg-[#161b22] cursor-pointer" : "cursor-default"
        }`}
      >
        {dot}
        <span className="text-sm font-medium text-[#f9fafb] flex-1">
          {STAGE_LABELS[group.stage] ?? group.stage}
        </span>
        {ts && <span className="text-xs text-[#4b5563]">{ts}</span>}
        {hasContent && (
          <span className="text-[#374151] text-xs ml-1">{open ? "▾" : "▸"}</span>
        )}
      </button>

      {open && hasContent && (
        <div className="bg-[#0d1117] border-t border-[#1f2937] py-1">
          {group.fetchRows.map((row) => (
            <FetchRowItem key={row.id} row={row} />
          ))}
          {group.thoughts.map((t) => (
            <ThoughtRowItem key={t.id} thought={t} />
          ))}
          {group.errorEvent && (
            <div className="px-4 py-1.5 text-xs text-[#ef4444]">
              ✕ {(group.errorEvent.message as string) ?? "unknown error"}
            </div>
          )}
          {group.completionEvent && (
            <CompletionSummary event={group.completionEvent} />
          )}
        </div>
      )}
    </div>
  );
}

// --- Page ---

export default function ActivityPage() {
  const { activityEvents, wsMessages, stage, status } = useSessionStore();

  const groups = buildGroups(activityEvents, wsMessages, stage, status);
  const hasAny =
    activityEvents.length > 0 ||
    wsMessages.some((m) => ["thought", "tool_call", "tool_result"].includes(m.type as string));

  if (!hasAny) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        {status === "running"
          ? "Processing… events will appear here"
          : "No activity yet — create or upload data to start"}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full p-4 gap-2 overflow-auto">
      {groups.map((group, idx) => (
        <StageCard
          key={`${group.stage}-${idx}`}
          group={group}
          defaultOpen={group.status === "active"}
        />
      ))}
    </div>
  );
}
