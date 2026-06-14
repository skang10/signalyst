"use client";

import { useEffect, useState } from "react";
import { FeaturizerConfigEditor } from "./FeaturizerConfigEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
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

function summarizeConfig(config: FeaturizerConfig): string {
  const parts = [
    `Windows ${config.windows.join(", ")}d`,
    `Lags ${config.lags.join(", ")}d`,
    `${config.feature_families.length} feature ${
      config.feature_families.length === 1 ? "family" : "families"
    }`,
  ];
  if (config.energy_specific) parts.push("energy-specific");
  return parts.join(" · ");
}

type UserReviewGateProps = {
  sessionId: string;
  serverConfig: FeaturizerConfig;
  onProceed: (patch?: FeaturizerConfig) => void;
  proceeding: boolean;
  onDirtyChange: (dirty: boolean) => void;
};

export function UserReviewGate({
  sessionId,
  serverConfig,
  onProceed,
  proceeding,
  onDirtyChange,
}: UserReviewGateProps) {
  const [draft, setDraft] = useState(serverConfig);
  const [expanded, setExpanded] = useState(false);
  const setSession = useSessionStore((s) => s.setSession);

  const handleConfigChange = (next: FeaturizerConfig) => {
    setDraft(next);
    api
      .updateConfig(sessionId, { featurizer_config_patch: next })
      .then(() => api.getSession(sessionId))
      .then(setSession)
      .catch(() => {});
  };
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

  if (!expanded) {
    return (
      <div className="w-full flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
        <span className="text-xs text-gray-500 flex-1 truncate">{summarizeConfig(draft)}</span>
        {isDirty && (
          <span className="text-xs text-amber-600 flex-shrink-0">edited</span>
        )}
        <button
          onClick={() => setExpanded(true)}
          className="text-xs text-brand hover:underline flex-shrink-0"
        >
          Edit
        </button>
        <button
          onClick={() => onProceed(isDirty ? draft : undefined)}
          disabled={proceeding}
          className="px-4 py-1.5 bg-brand border border-brand-hover rounded-full text-white text-xs font-semibold hover:bg-brand-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
        >
          {proceeding ? "Starting…" : "→ Run Analysis"}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-[85%] flex flex-col gap-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold tracking-widest text-gray-400 uppercase">
          Featurizer config
        </span>
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-gray-400 hover:text-gray-600 hover:underline"
        >
          Collapse
        </button>
      </div>

      <FeaturizerConfigEditor value={draft} onChange={handleConfigChange} />

      {isDirty && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
          <span className="flex-1">Config changed — Run Analysis to apply, or discard your edits</span>
          <button onClick={() => setDraft(serverConfig)} className="text-amber-600 hover:underline">
            Discard
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onProceed(isDirty ? draft : undefined)}
          disabled={proceeding}
          className="px-4 py-2 bg-brand border border-brand-hover rounded-full text-white text-sm font-semibold hover:bg-brand-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {proceeding ? "Starting…" : "→ Run Analysis"}
        </button>
      </div>
    </div>
  );
}
