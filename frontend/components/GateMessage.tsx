"use client";

import { useEffect, useState } from "react";
import { FeaturizerConfigEditor } from "./FeaturizerConfigEditor";
import type { FeaturizerConfig } from "@/lib/api";

function arraysEqual<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function configsEqual(a: FeaturizerConfig, b: FeaturizerConfig): boolean {
  return (
    arraysEqual(a.windows, b.windows) &&
    arraysEqual(a.lags, b.lags) &&
    arraysEqual(a.feature_families, b.feature_families) &&
    a.energy_specific === b.energy_specific
  );
}

type UserReviewGateProps = {
  serverConfig: FeaturizerConfig;
  onProceed: (patch?: FeaturizerConfig) => void;
  proceeding: boolean;
  onDirtyChange: (dirty: boolean) => void;
};

export function UserReviewGate({
  serverConfig,
  onProceed,
  proceeding,
  onDirtyChange,
}: UserReviewGateProps) {
  const [draft, setDraft] = useState(serverConfig);
  const [syncedConfig, setSyncedConfig] = useState(serverConfig);
  const isDirty = !configsEqual(draft, serverConfig);

  // Resync local edits whenever the server config changes from outside
  // (e.g. a chat-driven `update_config`), so the editor doesn't show stale values.
  // Adjusted during render (React's recommended pattern) rather than in an effect,
  // to avoid an extra render pass — see https://react.dev/learn/you-might-not-need-an-effect
  if (!configsEqual(syncedConfig, serverConfig)) {
    setSyncedConfig(serverConfig);
    setDraft(serverConfig);
  }

  // Notify the parent so the chat input can be disabled while edits are unsaved —
  // this is what keeps the structured-edit and free-text-chat paths from racing
  // (see "The chat/editor boundary" in the design doc).
  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  return (
    <div className="self-end max-w-[85%] flex flex-col gap-3 bg-[#0d1117] border border-[#21262d] rounded-lg p-3">
      <FeaturizerConfigEditor value={draft} onChange={setDraft} />

      {isDirty && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 bg-[#1c1009] border border-[#92400e] rounded text-xs text-[#fbbf24]">
          <span className="flex-1">Config changed — Run Analysis to apply, or discard your edits</span>
          <button onClick={() => setDraft(serverConfig)} className="text-[#f97316] hover:underline">
            Discard
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onProceed(isDirty ? draft : undefined)}
          disabled={proceeding}
          className="px-4 py-2 bg-[#052e16] border border-[#15803d] rounded-full text-[#22c55e] text-sm font-semibold hover:bg-[#14532d] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {proceeding ? "Starting…" : "→ Run Analysis"}
        </button>
      </div>
    </div>
  );
}
