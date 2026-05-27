import type { AgentProgressState, AgentPhase, EvidenceTone } from "@/lib/agentProgress";

interface Props {
  state: AgentProgressState;
  isRunning: boolean;
  connected: boolean;
}

const TONE_CHIP: Record<EvidenceTone, string> = {
  default: "bg-slate-800 text-slate-300",
  success: "bg-emerald-950 text-emerald-400",
  accent: "bg-violet-950 text-violet-400",
  warning: "bg-amber-950 text-amber-400",
  danger: "bg-red-950 text-red-400",
};

export function AgentProgressTimeline({ state, isRunning, connected }: Props) {
  const allWaiting = state.phases.every((p) => p.status === "waiting");

  if (!isRunning && allWaiting) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-400 text-sm text-center">
          Run an analysis to see the agent&apos;s reasoning.
        </p>
      </div>
    );
  }

  if (isRunning && !connected && allWaiting) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-500 text-xs animate-pulse">
          Connecting…
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4">
      {state.phases.map((phase, i) => (
        <PhaseRow
          key={phase.id}
          phase={phase}
          isLast={i === state.phases.length - 1}
        />
      ))}
    </div>
  );
}

function PhaseRow({ phase, isLast }: { phase: AgentPhase; isLast: boolean }) {
  const isWaiting = phase.status === "waiting";
  const latestNote = phase.notes[phase.notes.length - 1];

  return (
    <div
      data-phase-row={phase.id}
      className={`grid grid-cols-[22px_1fr] gap-3 ${isWaiting ? "opacity-[0.35]" : ""}`}
    >
      <div className="flex flex-col items-center">
        <PhaseIcon status={phase.status} />
        {!isLast && (
          <div
            className={`w-0.5 flex-1 min-h-8 mt-1 mb-1 ${
              phase.status === "done"
                ? "bg-slate-700"
                : phase.status === "running"
                ? "bg-slate-800"
                : "bg-slate-900"
            }`}
          />
        )}
      </div>
      <div className="pb-4 min-w-0">
        <p
          className={`text-sm font-semibold leading-[22px] ${
            phase.status === "running"
              ? "text-violet-400"
              : phase.status === "failed" || phase.status === "canceled"
              ? "text-red-400"
              : "text-slate-400"
          }`}
        >
          {phase.title}
        </p>

        <p className="mt-0.5 text-xs leading-5 text-slate-500">{phase.description}</p>

        {phase.status === "running" && latestNote && (
          <p className="mt-1.5 text-xs italic text-slate-400">{latestNote}</p>
        )}

        {phase.status === "running" && phase.progress && (
          <ProgressBar progress={phase.progress} />
        )}

        {phase.status === "done" && phase.evidence.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {phase.evidence.map((ev) => (
              <span
                key={`${ev.label}-${ev.value}`}
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${TONE_CHIP[ev.tone ?? "default"]}`}
              >
                {ev.label}: {ev.value}
              </span>
            ))}
          </div>
        )}

        {phase.status === "done" && phase.notes.length > 0 && phase.evidence.length === 0 && (
          <p className="mt-1 text-xs text-slate-500">{phase.notes[phase.notes.length - 1]}</p>
        )}
      </div>
    </div>
  );
}

function PhaseIcon({ status }: { status: AgentPhase["status"] }) {
  if (status === "done") {
    return (
      <div
        data-phase-dot
        className="h-[22px] w-[22px] rounded-full bg-emerald-600 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0"
      >
        ✓
      </div>
    );
  }
  if (status === "running") {
    return (
      <div
        data-phase-dot
        className="h-[22px] w-[22px] rounded-full bg-violet-700 flex items-center justify-center text-white text-[11px] flex-shrink-0 animate-pulse ring-2 ring-violet-900 ring-offset-1 ring-offset-[#0f0f1a]"
      >
        ⋯
      </div>
    );
  }
  if (status === "failed" || status === "canceled") {
    return (
      <div
        data-phase-dot
        className="h-[22px] w-[22px] rounded-full bg-red-600 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0"
      >
        ✕
      </div>
    );
  }
  return (
    <div
      data-phase-dot
      className="h-[22px] w-[22px] rounded-full border-2 border-slate-700 flex-shrink-0"
    />
  );
}

function ProgressBar({
  progress,
}: {
  progress: NonNullable<AgentPhase["progress"]>;
}) {
  const pct = progress.unknownTotal
    ? null
    : Math.min(100, (progress.completed / Math.max(progress.total, 1)) * 100);

  return (
    <div className="mt-2">
      <div className="h-1 w-full rounded-full bg-slate-800 overflow-hidden">
        {pct !== null ? (
          <div
            className="h-full bg-violet-500 rounded-full transition-[width]"
            style={{ width: `${pct}%` }}
          />
        ) : (
          <div className="h-full w-1/3 bg-violet-500 rounded-full animate-pulse" />
        )}
      </div>
      <p className="mt-1 text-[11px] text-slate-600 text-right">
        {progress.unknownTotal
          ? `${progress.completed} calls`
          : `${progress.completed} / ${progress.total}`}
      </p>
    </div>
  );
}
