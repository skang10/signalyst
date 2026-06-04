"use client";

import type { SessionStage } from "@/lib/api";

const STAGES: { key: SessionStage; label: string }[] = [
  { key: "configuring", label: "CONFIG" },
  { key: "data_gathering", label: "DATA" },
  { key: "user_review", label: "REVIEW" },
  { key: "featurizing", label: "FEATURES" },
  { key: "analyzing", label: "ANALYZE" },
  { key: "explaining", label: "EXPLAIN" },
  { key: "follow_up", label: "FOLLOW-UP" },
];

const STAGE_ORDER = STAGES.map((s) => s.key);

type Props = { currentStage: SessionStage | null };

export function StageStrip({ currentStage }: Props) {
  const currentIdx = currentStage ? STAGE_ORDER.indexOf(currentStage) : -1;

  return (
    <div className="flex items-center px-4 py-2 border-b border-[#21262d] bg-[#111827] gap-1">
      {STAGES.map((stage, idx) => {
        const isDone = idx < currentIdx;
        const isActive = idx === currentIdx;
        const isPending = idx > currentIdx;

        return (
          <div key={stage.key} className="flex flex-col items-center flex-1">
            <div
              className={[
                "h-1 w-full rounded-full",
                isDone ? "bg-[#22c55e]" : "",
                isActive ? "bg-[#3b82f6] animate-pulse" : "",
                isPending ? "bg-[#374151]" : "",
              ].join(" ")}
            />
            <span
              className={[
                "text-[10px] mt-1 font-mono tracking-wider",
                isDone ? "text-[#22c55e]" : "",
                isActive ? "text-[#60a5fa]" : "",
                isPending ? "text-[#4b5563]" : "",
              ].join(" ")}
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
