"use client";

import { useEffect, useRef } from "react";
import { useRunStore } from "@/lib/store";
import type { StreamMessage } from "@/lib/websocket";

export function ThoughtStream() {
  const { messages } = useRunStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-500 text-sm animate-pulse">Connecting to agent…</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-1 font-mono text-xs">
      {messages.map((msg, i) => (
        <MessageLine key={i} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageLine({ msg }: { msg: StreamMessage }) {
  switch (msg.type) {
    case "phase":
      return (
        <div className="pt-3 pb-0.5 text-[10px] text-slate-600 uppercase tracking-widest">
          ── {msg.phase.replace(/_/g, " ")} ──
        </div>
      );
    case "thought":
      return (
        <div className="flex gap-2 text-slate-300 leading-relaxed">
          <span className="text-violet-500 shrink-0">→</span>
          <span>{msg.content}</span>
        </div>
      );
    case "tool_call":
      return (
        <div className="flex gap-2 text-slate-600">
          <span className="shrink-0">⚙</span>
          <span>
            {msg.tool}
            <span className="text-slate-700 ml-1">({compactInput(msg.input)})</span>
          </span>
        </div>
      );
    case "tool_result":
      return (
        <div className="flex gap-2 text-emerald-700">
          <span className="shrink-0">✓</span>
          <span>{msg.tool} returned</span>
        </div>
      );
    case "done":
      return (
        <div className="pt-3 flex gap-2 text-emerald-400">
          <span>◉</span>
          <span>Analysis complete</span>
        </div>
      );
    default:
      return null;
  }
}

function compactInput(input: unknown): string {
  if (typeof input !== "object" || input === null) return String(input);
  const keys = Object.keys(input as Record<string, unknown>);
  if (keys.length === 0) return "";
  return keys.slice(0, 2).join(", ") + (keys.length > 2 ? ", …" : "");
}
