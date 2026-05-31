"use client";

import { useRef, useState } from "react";
import { useRunStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/store";

const EXAMPLE_CHIPS = [
  "Why is drift elevated?",
  "Explain the regime classification",
  "Add Baker Hughes rig count data",
  "What are the top features driving this?",
];

export function ChatPanel() {
  const {
    chatOpen,
    chatMessages,
    status,
    runId,
    lastRunParams,
    setChatOpen,
    addChatMessage,
    queuePreRunMessage,
    continueToRun,
  } = useRunStore();
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  if (!chatOpen) return null;

  const isInputDisabled =
    status === "running" || status === "failed" || status === "canceled";

  const placeholder =
    status === "running"
      ? "Agent is working — message will be queued"
      : status === "completed"
        ? "Ask a follow-up question…"
        : status === "failed" || status === "canceled"
          ? "Run ended"
          : "Ask the agent — add a connector, set context…";

  const showChips = status === "completed" && chatMessages.length === 0;

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isInputDisabled || isSending) return;

    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };

    if (status === "completed" && runId && lastRunParams) {
      setIsSending(true);
      setInput("");
      addChatMessage(msg);
      try {
        const { run_id } = await api.continueRun(runId, trimmed);
        continueToRun(run_id, lastRunParams);
      } catch {
        // continuation failed — status stays completed, user message preserved in chat
      } finally {
        setIsSending(false);
      }
    } else {
      addChatMessage(msg);
      if (status === "idle") queuePreRunMessage(trimmed);
      setInput("");
    }

    setTimeout(() => bottomRef.current?.scrollIntoView?.({ behavior: "smooth" }), 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <aside className="w-[280px] border-l border-slate-800 flex flex-col bg-[#0f0f1a] shrink-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
        <span className="text-sm font-semibold text-slate-300">Chat</span>
        <button
          onClick={() => setChatOpen(false)}
          className="text-slate-500 hover:text-slate-300 text-sm leading-none"
          aria-label="Close chat"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 min-h-0 flex flex-col justify-end gap-2">
        {chatMessages.length === 0 && !showChips && (
          <p className="text-xs text-slate-500 text-center">
            Messages appear here.
          </p>
        )}
        {showChips && (
          <div className="flex flex-col gap-1 mb-2">
            <p className="text-xs text-slate-500 text-center mb-1">Try asking…</p>
            {EXAMPLE_CHIPS.map((chip) => (
              <button
                key={chip}
                onClick={() => setInput(chip)}
                className="text-left text-xs px-2 py-1.5 rounded border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-300 transition-colors"
              >
                {chip}
              </button>
            ))}
          </div>
        )}
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-lg px-3 py-2 max-w-[85%] text-sm"
                  : "bg-slate-800 text-slate-200 rounded-lg px-3 py-2 max-w-[85%] text-sm"
              }
            >
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-800 p-2 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isInputDisabled}
          placeholder={placeholder}
          rows={2}
          className={
            "flex-1 resize-none rounded border border-slate-700 bg-slate-900 text-slate-100 " +
            "text-sm px-2 py-1 focus:outline-none focus:ring-1 focus:ring-violet-500 " +
            "disabled:opacity-50 disabled:cursor-not-allowed"
          }
        />
        <button
          onClick={handleSend}
          disabled={isInputDisabled || isSending || !input.trim()}
          aria-label="Send message"
          className={
            "px-2 py-1 rounded bg-violet-600 hover:bg-violet-700 text-white text-sm " +
            "font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          }
        >
          ↑
        </button>
      </div>
    </aside>
  );
}
