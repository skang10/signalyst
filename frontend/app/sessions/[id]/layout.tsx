"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Results", path: "results" },
];

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm leading-relaxed ${
          isUser
            ? "bg-[#1d4ed8] text-white rounded-br-sm"
            : "bg-[#1f2937] text-[#f9fafb] rounded-bl-sm"
        }`}
      >
        {msg.content}
      </div>
    </div>
  );
}

function ChatPanel({
  sessionId,
  conversation,
  status,
  onSent,
}: {
  sessionId: string;
  conversation: ChatMessage[];
  status: string | null;
  onSent: () => void;
}) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.length]);

  const handleSend = async () => {
    const text = message.trim();
    if (!text || sending) return;
    setMessage("");
    setSending(true);
    setError(null);
    try {
      await api.sendChat(sessionId, text);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const disabled = sending || status !== "waiting";

  return (
    <div className="border-t border-[#21262d] bg-[#0d1117] flex flex-col" style={{ height: "220px" }}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#21262d]">
        <span className="text-xs text-[#4b5563] uppercase tracking-wider">Review</span>
        <span className="text-xs text-[#6b7280]">·</span>
        <span className="text-xs text-[#6b7280]">
          Ask to add data, adjust settings, or say &ldquo;run analysis&rdquo;
        </span>
      </div>

      {/* Conversation history */}
      <div className="flex-1 overflow-auto px-3 py-2 flex flex-col gap-2">
        {conversation.length === 0 && (
          <div className="flex flex-col gap-1 text-xs text-[#4b5563] mt-1">
            <span>Examples:</span>
            <span className="font-mono">&ldquo;Add Baker Hughes rig count data&rdquo;</span>
            <span className="font-mono">&ldquo;Use 30-day rolling windows&rdquo;</span>
            <span className="font-mono">&ldquo;Looks good, run the analysis&rdquo;</span>
          </div>
        )}
        {conversation.map((msg, i) => (
          <ChatBubble key={i} msg={msg} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#1f2937] text-[#6b7280] text-xs px-3 py-2 rounded-lg rounded-bl-sm">
              Thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input row */}
      <div className="border-t border-[#21262d] px-3 py-2 flex gap-2 items-center">
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
          placeholder="Type a message…"
          disabled={disabled}
          className="flex-1 bg-[#111827] border border-[#21262d] rounded px-3 py-1.5 text-sm text-[#f9fafb] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6] disabled:opacity-40"
        />
        <button
          onClick={handleSend}
          disabled={!message.trim() || disabled}
          className="px-4 py-1.5 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
      {error && <p className="text-xs text-[#ef4444] px-3 pb-1.5">{error}</p>}
    </div>
  );
}

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const { sessionId, stage, status, conversation, setSession } = useSessionStore();
  const [canceling, setCanceling] = useState(false);

  useSessionStream(id ?? null);

  // Initial fetch
  useEffect(() => {
    if (!id) return;
    api
      .getSession(id)
      .then(setSession)
      .catch(() => router.push("/"));
  }, [id, router, setSession]);

  // Poll while a background task is running (WS stub doesn't push events yet)
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
      // Refresh session state after cancel
      const updated = await api.getSession(id);
      setSession(updated);
    } catch {
      // swallow — status will update on next poll/WS event
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#060b14] text-[#f9fafb]">
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">■ SIGNALYST</span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-[#21262d] text-[#9ca3af] hover:text-[#f9fafb] transition-colors"
        >
          + NEW ANALYSIS
        </Link>
      </header>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <Link href="/" className="text-[#9ca3af] hover:text-[#f9fafb] text-sm transition-colors">
          ← Sessions
        </Link>
        {sessionId && (
          <>
            <span className="text-[#6b7280] text-xs">·</span>
            <span className="text-sm text-[#9ca3af] font-mono">{id?.slice(0, 8)}</span>
            {stage && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#1f2937] text-[#60a5fa] border border-[#1d4ed8]">
                {stage}
              </span>
            )}
            {status && (
              <span
                className={[
                  "text-xs",
                  status === "running" ? "text-[#22c55e]" : "",
                  status === "waiting" ? "text-[#9ca3af]" : "",
                  status === "failed" ? "text-[#ef4444]" : "",
                  status === "canceled" ? "text-[#f59e0b]" : "",
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
                className="ml-auto text-xs px-2 py-0.5 rounded border border-[#ef4444] text-[#ef4444] hover:bg-[#ef4444] hover:text-white transition-colors disabled:opacity-40"
              >
                {canceling ? "Canceling…" : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>

      <StageStrip currentStage={stage} />

      <div className="flex gap-4 px-4 border-b border-[#21262d] bg-[#111827]">
        {TABS.map((tab) => {
          const href = `/sessions/${id}/${tab.path}`;
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
                title={`Locked — not available at this stage`}
                className="text-sm py-2 border-b-2 border-transparent text-[#374151] cursor-not-allowed select-none"
              >
                {tab.label}
              </span>
            );
          }

          return (
            <Link
              key={tab.label}
              href={href}
              className={[
                "text-sm py-2 border-b-2 transition-colors",
                isActive
                  ? "border-[#3b82f6] text-[#f9fafb]"
                  : "border-transparent text-[#9ca3af] hover:text-[#f9fafb]",
              ].join(" ")}
            >
              {tab.label}{badge}
            </Link>
          );
        })}
      </div>

      <main className="flex-1 overflow-auto min-h-0">{children}</main>

      {stage === "user_review" && id && (
        <ChatPanel
          sessionId={id}
          conversation={conversation}
          status={status}
          onSent={() => api.getSession(id).then(setSession).catch(() => {})}
        />
      )}
    </div>
  );
}
