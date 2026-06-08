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
    <div className="flex items-center px-4 py-2 border-b border-gray-200 bg-gray-50 gap-1">
      {STAGES.map((stage, idx) => {
        const isDone = idx < currentIdx;
        const isActive = idx === currentIdx;
        const isPending = idx > currentIdx;

        return (
          <div key={stage.key} className="flex flex-col items-center flex-1">
            <div
              className={[
                "h-1 w-full rounded-full",
                isDone ? "bg-green-500" : "",
                isActive ? "bg-teal-500 animate-pulse" : "",
                isPending ? "bg-gray-200" : "",
              ].join(" ")}
            />
            <span
              className={[
                "text-[10px] mt-1 font-mono tracking-wider",
                isDone ? "text-green-600" : "",
                isActive ? "text-teal-600" : "",
                isPending ? "text-gray-400" : "",
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
