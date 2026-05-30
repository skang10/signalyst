"use client";

import { useRef, useState } from "react";
import { useRunStore } from "@/lib/store";
import type { ChatMessage } from "@/lib/store";

export function ChatPanel() {
  const { chatOpen, chatMessages, status, setChatOpen, addChatMessage, queuePreRunMessage } =
    useRunStore();
  const [input, setInput] = useState("");
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

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isInputDisabled) return;

    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };
    addChatMessage(msg);
    if (status === "idle") {
      queuePreRunMessage(trimmed);
    }
    setInput("");
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
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

      <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
        {chatMessages.length === 0 && (
          <p className="text-xs text-slate-500 text-center mt-4">
            Messages appear here.
          </p>
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
          disabled={isInputDisabled || !input.trim()}
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
