"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/api";
import { buildGroups } from "@/lib/activity-groups";
import type { FetchRow, StageGroup, ThoughtEntry } from "@/lib/activity-groups";
import { useSessionStore } from "@/lib/store";

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
            <span className="text-[#9ca3af] break-all">{JSON.stringify(row.input)}</span>
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

// --- Chat message ---

function ChatMessageItem({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex px-4 py-1.5 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-xs leading-relaxed ${
          isUser
            ? "bg-[#1d4ed8] text-white rounded-br-sm"
            : "bg-[#1f2937] text-[#f9fafb] rounded-bl-sm border border-[#374151]"
        }`}
      >
        {msg.content}
      </div>
    </div>
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
            <span className="text-[#166534] ml-1">
              ({tickers.slice(0, 4).join(", ")}{tickers.length > 4 ? ` +${tickers.length - 4}` : ""})
            </span>
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
  const { activityEvents, wsMessages, conversation, stage, status, sessionId, setSession } =
    useSessionStore();
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const groups = buildGroups(activityEvents, wsMessages, conversation, stage, status);
  const hasAny =
    activityEvents.length > 0 ||
    conversation.length > 0 ||
    wsMessages.some((m) => ["thought", "tool_call", "tool_result"].includes(m.type as string));

  const handleSend = async () => {
    const text = message.trim();
    if (!text || sending || !sessionId) return;
    setMessage("");
    setSending(true);
    setSendError(null);
    try {
      await api.sendChat(sessionId, text);
      const updated = await api.getSession(sessionId);
      setSession(updated);
    } catch (e) {
      setSendError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const showInput = stage === "user_review";
  const inputDisabled = sending || status !== "waiting";

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto min-h-0 p-4 flex flex-col gap-2">
        {!hasAny ? (
          <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
            {status === "running"
              ? "Processing… events will appear here"
              : "No activity yet — create or upload data to start"}
          </div>
        ) : (
          groups.map((group, idx) => (
            <div key={`${group.stage}-${idx}`} className="flex flex-col gap-2">
              <StageCard group={group} defaultOpen={group.status === "active"} />
              {group.chatMessages.map((msg, i) => (
                <ChatMessageItem key={`chat-${idx}-${i}`} msg={msg} />
              ))}
            </div>
          ))
        )}
      </div>

      {showInput && (
        <div className="border-t border-[#21262d] bg-[#0d1117] px-4 py-3 flex flex-col gap-1.5 flex-shrink-0">
          <div className="flex gap-2 items-center">
            <input
              ref={inputRef}
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={
                status === "running"
                  ? "Agent is thinking…"
                  : "Ask to adjust data, or say “run analysis”"
              }
              disabled={inputDisabled}
              className="flex-1 bg-[#111827] border border-[#21262d] rounded-lg px-3 py-2 text-sm text-[#f9fafb] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6] disabled:opacity-40"
            />
            <button
              onClick={handleSend}
              disabled={!message.trim() || inputDisabled}
              className="px-4 py-2 rounded-lg bg-[#1d4ed8] hover:bg-[#2563eb] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ↑
            </button>
          </div>
          {sendError && <p className="text-xs text-[#ef4444]">{sendError}</p>}
        </div>
      )}
    </div>
  );
}
