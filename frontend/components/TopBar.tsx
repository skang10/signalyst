"use client";

import { useState, useEffect } from "react";
import { useRunStore } from "@/lib/store";
import { api } from "@/lib/api";

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  canceled: { label: "Canceled", color: "#f97316" },
  failed: { label: "Failed", color: "#ef4444" },
  completed: { label: "Completed", color: "#22c55e" },
};

export function TopBar() {
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [mode, setMode] = useState<"quick" | "full">("quick");
  const [topbarError, setTopbarError] = useState<string | null>(null);

  const { runId, status, setRun, setCanceled, setStatus, hydrate } = useRunStore();

  useEffect(() => { hydrate(); }, [hydrate]);

  const isRunning = status === "running";
  const hasStoppedRun = status !== "running" && runId !== null;
  const badge = STATUS_BADGE[status] ?? null;

  const handleRun = async () => {
    setTopbarError(null);
    try {
      const { run_id } = await api.analyze({
        date_range_start: start,
        date_range_end: end,
        analysis_mode: mode,
      });
      setRun(run_id, { date_range_start: start, date_range_end: end, analysis_mode: mode });
    } catch (e) {
      setTopbarError(e instanceof Error ? e.message : "Failed to start analysis");
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await api.cancelRun(runId);
    } catch {
      // swallow API errors — client-side cancellation proceeds regardless
    } finally {
      setCanceled();
    }
  };

  const handleResume = () => {
    setStatus("running");
  };

  const inputClass =
    "rounded border border-slate-700 bg-slate-900 text-slate-100 text-sm px-2 py-1 " +
    "focus:outline-none focus:ring-1 " +
    "focus:ring-violet-500";

  const pillBase = "text-sm px-3 py-1 rounded-full border transition-colors";
  const pillActive =
    "border-violet-500 bg-violet-950 text-violet-300 font-semibold";
  const pillInactive =
    "border-slate-700 text-slate-400 hover:border-slate-400";

  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 border-b border-slate-800 bg-[#0f0f1a] flex-wrap">
      <span className="font-bold text-white text-base mr-1">
        Signalyst
      </span>

      <input
        type="date"
        value={start}
        onChange={(e) => setStart(e.target.value)}
        className={inputClass}
        disabled={isRunning}
      />
      <span className="text-slate-400 text-sm">→</span>
      <input
        type="date"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
        className={inputClass}
        disabled={isRunning}
      />

      <div className="flex gap-1">
        <button
          onClick={() => setMode("quick")}
          className={`${pillBase} ${mode === "quick" ? pillActive : pillInactive}`}
          disabled={isRunning}
        >
          Quick
        </button>
        <button
          onClick={() => setMode("full")}
          className={`${pillBase} ${mode === "full" ? pillActive : pillInactive}`}
          disabled={isRunning}
        >
          Full
        </button>
      </div>

      <div className="flex gap-2 ml-auto items-center">
        {topbarError && (
          <span className="text-xs text-red-500">{topbarError}</span>
        )}

        {isRunning ? (
          <button
            onClick={handleCancel}
            className="text-sm px-4 py-1.5 rounded bg-red-500 hover:bg-red-600 text-white font-semibold transition-colors"
          >
            ✕ Cancel
          </button>
        ) : hasStoppedRun ? (
          <>
            {badge && (
              <span className="text-xs flex items-center gap-1" style={{ color: badge.color }}>
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: badge.color }}
                />
                {badge.label}
              </span>
            )}
            <button
              onClick={handleResume}
              className="text-sm px-4 py-1.5 rounded border border-slate-600 text-slate-300 font-semibold hover:border-slate-500 transition-colors"
            >
              ↩ Resume
            </button>
            <button
              onClick={handleRun}
              className="text-sm px-4 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white font-semibold transition-colors"
            >
              ▶ New Run
            </button>
          </>
        ) : (
          <button
            onClick={handleRun}
            className="text-sm px-4 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white font-semibold transition-colors"
          >
            ▶ Run
          </button>
        )}
      </div>
    </header>
  );
}
