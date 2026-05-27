"use client";

import { useRunStore } from "@/lib/store";
import { buildAgentProgress } from "@/lib/agentProgress";
import { AgentProgressTimeline } from "./AgentProgressTimeline";

interface Props {
  isOpen: boolean;
}

export function AgentDrawer({ isOpen }: Props) {
  const { messages, status } = useRunStore();
  const progress = buildAgentProgress(messages);
  const isRunning = status === "running";
  const connected = messages.length > 0;

  return (
    <aside
      className={`border-l border-slate-800 bg-[#090914] transition-[width,opacity] duration-200 overflow-hidden shrink-0 ${
        isOpen ? "w-[390px] opacity-100" : "w-0 opacity-0"
      }`}
    >
      <div className="flex h-full w-[390px] flex-col">
        <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-800 px-4">
          <h2 className="text-sm font-semibold text-slate-200">Agent progress</h2>
          <span className="text-xs text-slate-600">{isRunning ? "Running" : "Timeline"}</span>
        </div>
        <AgentProgressTimeline
          state={progress}
          isRunning={isRunning}
          connected={connected}
        />
      </div>
    </aside>
  );
}
