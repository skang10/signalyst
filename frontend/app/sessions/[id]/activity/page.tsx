"use client";

import { useSessionStore } from "@/lib/store";

const EVENT_ICONS: Record<string, string> = {
  stage_transition: "→",
  artifact_ready: "✓",
  cache_hit: "⚡",
  error: "✕",
  canceled: "◌",
};

const STAGE_LABELS: Record<string, string> = {
  configuring: "Config",
  data_gathering: "Data Gathering",
  user_review: "User Review",
  featurizing: "Featurizing",
  analyzing: "Analyzing",
  explaining: "Explaining",
  follow_up: "Follow-up",
};

function EventRow({ event }: { event: Record<string, unknown> }) {
  const type = event.type as string;
  const icon = EVENT_ICONS[type] ?? "·";
  const ts = event.created_at
    ? new Date(event.created_at as string).toLocaleTimeString()
    : "";

  let label = type.replace(/_/g, " ");
  if (type === "stage_transition") {
    label = `${STAGE_LABELS[(event.to as string) ?? ""] ?? event.to} started`;
  } else if (type === "artifact_ready") {
    const kind = event.kind as string;
    const rows = event.rows ? ` · ${event.rows} rows` : "";
    const features = event.n_features ? ` · ${event.n_features} features` : "";
    label = `${kind} artifact ready${rows}${features}`;
  } else if (type === "cache_hit") {
    label = `cache hit at ${event.stage}`;
  } else if (type === "error") {
    label = `error: ${event.message}`;
  }

  return (
    <div className="flex items-start gap-3 py-2 border-b border-[#1f2937] last:border-0">
      <span
        className={[
          "text-xs w-4 mt-0.5 flex-shrink-0",
          type === "error" ? "text-[#ef4444]" : "text-[#3b82f6]",
        ].join(" ")}
      >
        {icon}
      </span>
      <span className="text-sm text-[#f9fafb] flex-1">{label}</span>
      <span className="text-xs text-[#6b7280] flex-shrink-0">{ts}</span>
    </div>
  );
}

export default function ActivityPage() {
  const { activityEvents, stage, status } = useSessionStore();

  const statusMsg: Record<string, string> = {
    running: "Running…",
    waiting: "Waiting for input",
    failed: "Failed",
    canceled: "Canceled",
  };

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      {activityEvents.length === 0 ? (
        <div className="flex items-center justify-center flex-1 text-[#4b5563] text-sm">
          {status === "running"
            ? "Processing… events will appear here"
            : "No activity yet — upload data or start an analysis"}
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <div className="bg-[#111827] rounded-lg border border-[#21262d] divide-y divide-[#1f2937]">
            {activityEvents.map((ev, i) => (
              <EventRow
                key={(ev.event_id as string) ?? i}
                event={ev as Record<string, unknown>}
              />
            ))}
          </div>
        </div>
      )}

      {stage && status && (
        <div className="text-xs text-[#6b7280]">
          {STAGE_LABELS[stage] ?? stage} · {statusMsg[status] ?? status}
        </div>
      )}
    </div>
  );
}
