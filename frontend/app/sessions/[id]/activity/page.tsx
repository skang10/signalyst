"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ChatMessage, FeaturizerConfig } from "@/lib/api";
import { buildGroups } from "@/lib/activity-groups";
import type { FetchRow, StageGroup, ThoughtEntry } from "@/lib/activity-groups";
import { useSessionStore } from "@/lib/store";
import { UserReviewGate } from "@/components/GateMessage";

// --- Labels ---

const STAGE_LABELS: Record<string, string> = {
  configuring: "Source Discovery",
  data_gathering: "Data Gathering",
  user_review: "User Review",
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
  list_available_connectors: () => "listed connectors",
  approve_sources: () => "approved sources",
  save_connector_spec: (i) => `saved connector · ${i.id ?? ""}`,
  http_get: (i) => `GET ${(i.url as string | undefined)?.replace(/^https?:\/\//, "") ?? ""}`,
  http_post: (i) => `POST ${(i.url as string | undefined)?.replace(/^https?:\/\//, "") ?? ""}`,
};

function toolLabel(tool: string, input: Record<string, unknown>): string {
  return TOOL_DISPLAY[tool]?.(input) ?? tool.replace(/_/g, " ");
}

// --- Stage pill ---

function StagePill({ group }: { group: StageGroup }) {
  const label = STAGE_LABELS[group.stage] ?? group.stage;
  const ts = group.startTime ? new Date(group.startTime).toLocaleTimeString() : "";

  const styles =
    group.status === "active"
      ? { wrap: "border-teal-200 bg-teal-50 text-teal-600", dot: "bg-teal-500 animate-pulse" }
      : group.status === "failed"
      ? { wrap: "border-red-200 bg-red-50 text-red-600", dot: "bg-red-500" }
      : { wrap: "border-green-200 bg-green-50 text-green-700", dot: "bg-green-500" };

  return (
    <div className="flex justify-center my-1">
      <div className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs ${styles.wrap}`}>
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${styles.dot}`} />
        <span>{label}</span>
        {ts && <span className="opacity-50">· {ts}</span>}
      </div>
    </div>
  );
}

// --- Inline refetch status (compact, for chat-triggered data gathering) ---

function InlineFetchStatus({ group }: { group: StageGroup }) {
  const labels = group.fetchRows.map((row) => toolLabel(row.tool, row.input));
  const rows = group.completionEvent?.rows as number | undefined;

  if (group.errorEvent) {
    return (
      <div className="self-start ml-10 inline-flex items-center gap-2 px-3 py-1.5 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md">
        ✕ {(group.errorEvent.message as string) ?? "Fetch failed"}
      </div>
    );
  }

  if (group.status === "active") {
    return (
      <div className="self-start ml-10 inline-flex items-center gap-2 px-3 py-1.5 text-xs text-teal-600 bg-teal-50 border border-teal-200 rounded-md">
        <span className="animate-spin leading-none">⟳</span>
        {labels.length > 0 ? `Fetching ${labels.join(", ")}…` : "Fetching new data…"}
      </div>
    );
  }

  if (group.completionEvent) {
    return (
      <div className="self-start ml-10 inline-flex items-center gap-2 px-3 py-1.5 text-xs text-green-700 bg-green-50 border border-green-200 rounded-md">
        ✓ {labels.length > 0 ? labels.join(", ") : "Data updated"}
        {rows !== undefined && ` · ${rows} rows`}
      </div>
    );
  }

  return null;
}

// --- Thinking block ---

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

// --- Tool chip ---

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

// --- Completion / error chip ---

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
    if (kind === "data") return null; // rendered by DataCompletionChip in AgentTurn
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

// --- Agent speech bubble (standalone, with avatar) ---

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

// --- Data completion chip (expandable, shows full ticker list + cache date) ---

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

// --- Agent turn (tools + thinking + completion only, no chat messages) ---

function AgentTurn({ group }: { group: StageGroup }) {
  const hasContent =
    group.thoughts.length > 0 ||
    group.fetchRows.length > 0 ||
    group.completionEvent !== null ||
    group.errorEvent !== null;

  if (!hasContent) return null;

  const isActive = group.status === "active";

  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5 bg-teal-600"
      >
        S
      </div>

      {/* Content */}
      <div className="flex flex-col gap-2 flex-1 min-w-0">
        <span className="text-xs text-gray-500 font-medium">Signalyst Agent</span>

        {group.thoughts.length > 0 && (
          <ThinkingBlock thoughts={group.thoughts} active={isActive} />
        )}

        {group.fetchRows.length > 0 && (
          <div className="flex flex-col gap-1">
            {group.fetchRows.map((row) => (
              <ToolChip key={row.id} row={row} />
            ))}
          </div>
        )}

        {group.completionEvent && (
          group.completionEvent.kind === "data"
            ? <DataCompletionChip event={group.completionEvent} cacheHitEvent={group.cacheHitEvent} />
            : <CompletionChip event={group.completionEvent} />
        )}

        {group.errorEvent && (
          <div className="text-xs text-red-600 px-3 py-1.5 bg-red-50 border border-red-200 rounded-md">
            ✕ {(group.errorEvent.message as string) ?? "unknown error"}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Agent thinking line (shown while waiting for response) ---

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

// --- User bubble ---

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

// --- Page ---

export default function ActivityPage() {
  const {
    activityEvents,
    wsMessages,
    conversation,
    stage,
    status,
    sessionId,
    featurizerConfig,
    setSession,
  } = useSessionStore();
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [optimisticMsg, setOptimisticMsg] = useState<ChatMessage | null>(null);
  const [proceeding, setProceeding] = useState(false);
  const [proceedError, setProceedError] = useState<string | null>(null);
  const [reviewConfigDirty, setReviewConfigDirty] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  // Append optimistic user message so it appears instantly on send
  const effectiveConversation: ChatMessage[] = optimisticMsg
    ? [...conversation, optimisticMsg]
    : conversation;

  const groups = buildGroups(activityEvents, wsMessages, effectiveConversation, stage, status);
  const hasAny =
    activityEvents.length > 0 ||
    effectiveConversation.length > 0 ||
    wsMessages.some((m) => ["thought", "tool_call", "tool_result"].includes(m.type as string));

  const handleSend = async () => {
    const text = message.trim();
    if (!text || sending || !sessionId) return;
    setMessage("");
    setSending(true);
    setSendError(null);
    setOptimisticMsg({ role: "user", content: text, created_at: new Date().toISOString() });
    try {
      await api.sendChat(sessionId, text);
      const updated = await api.getSession(sessionId);
      setSession(updated);
    } catch (e) {
      setSendError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setOptimisticMsg(null);
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleProceed = async (featurizerConfigPatch?: FeaturizerConfig) => {
    if (!sessionId || proceeding) return;
    setProceeding(true);
    setProceedError(null);
    try {
      await api.proceed(sessionId, featurizerConfigPatch);
      const updated = await api.getSession(sessionId);
      setSession(updated);
    } catch (e) {
      setProceedError(e instanceof Error ? e.message : "Failed to start analysis");
    } finally {
      setProceeding(false);
    }
  };

  const showInput = stage === "user_review" || stage === "data_gathering" || stage === "follow_up";
  const showRunAnalysis = stage === "user_review" && status === "waiting" && !sending;
  const inputDisabled =
    sending || status !== "waiting" || (stage === "user_review" && reviewConfigDirty);

  // Keep the feed pinned to the latest content as new events stream in.
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [activityEvents.length, wsMessages.length, effectiveConversation.length]);

  return (
    <div className="flex flex-col h-full">
      {/* Feed */}
      <div ref={feedRef} className="flex-1 overflow-auto min-h-0 px-4 py-4">
        {!hasAny ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            {status === "running"
              ? "Processing… events will appear here"
              : "No activity yet — create or upload data to start"}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {groups.map((group, idx) => {
              const isChatRefetch =
                group.stage === "data_gathering" && group.fromStage === "user_review";
              return (
              <div key={`${group.stage}-${idx}`} className="flex flex-col gap-3">
                {isChatRefetch ? (
                  <InlineFetchStatus group={group} />
                ) : (
                  <>
                    <StagePill group={group} />
                    <AgentTurn group={group} />
                  </>
                )}
                {/* Render chat messages in timestamp order, role determines component */}
                {group.chatMessages.map((msg, i) =>
                  msg.role === "assistant" ? (
                    <AgentSpeechBubble key={`chat-${idx}-${i}`} content={msg.content} />
                  ) : (
                    <UserBubble key={`chat-${idx}-${i}`} msg={msg} />
                  )
                )}
              </div>
              );
            })}
            {(sending || (stage === "follow_up" && status === "running")) && <AgentThinkingLine />}
          </div>
        )}
      </div>

      {/* Featurizer config review gate — pinned above the input, separate from the scrolling feed */}
      {showRunAnalysis && featurizerConfig && sessionId && (
        <div className="border-t border-gray-200 bg-white px-4 py-3 flex flex-col gap-1.5 flex-shrink-0">
          <div className="flex justify-end">
            <UserReviewGate
              key={JSON.stringify(featurizerConfig)}
              sessionId={sessionId}
              serverConfig={featurizerConfig}
              onProceed={handleProceed}
              proceeding={proceeding}
              onDirtyChange={setReviewConfigDirty}
            />
          </div>
          {proceedError && <p className="text-xs text-red-500 text-right">{proceedError}</p>}
        </div>
      )}

      {/* Input bar */}
      {showInput && (
        <div className="border-t border-gray-200 bg-white px-4 py-3 flex flex-col gap-1.5 flex-shrink-0">
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
                stage === "data_gathering" && status === "running"
                  ? "Fetching data..."
                  : status === "running"
                  ? "Agent is thinking..."
                  : stage === "user_review" && reviewConfigDirty
                  ? "Config changes pending — Run Analysis or Discard to continue chatting"
                  : stage === "follow_up"
                  ? "Ask about the results, or request a re-run with different settings"
                  : "Ask to adjust data, or say \"run analysis\""
              }
              disabled={inputDisabled}
              className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-teal-400 disabled:opacity-40"
            />
            <button
              onClick={handleSend}
              disabled={!message.trim() || inputDisabled}
              className="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ↑
            </button>
          </div>
          {sendError && <p className="text-xs text-red-500">{sendError}</p>}
        </div>
      )}
    </div>
  );
}
