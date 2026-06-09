"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import type { FeaturizerConfig } from "@/lib/api";

type SaveStatus = "idle" | "saving" | "saved" | "failed";

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const { featurizerConfig, stage, setSession } = useSessionStore();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [pendingConfig, setPendingConfig] = useState<FeaturizerConfig | null>(null);

  useEffect(() => {
    if (status !== "saved") return;
    const timeout = setTimeout(() => setStatus("idle"), 2000);
    return () => clearTimeout(timeout);
  }, [status]);

  if (!featurizerConfig) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  const handleChange = async (next: FeaturizerConfig) => {
    if (!id) return;
    setStatus("saving");
    setPendingConfig(next);
    try {
      await api.updateConfig(id, next);
      const updated = await api.getSession(id);
      setSession(updated);
      setStatus("saved");
      setPendingConfig(null);
    } catch {
      setStatus("failed");
    }
  };

  const handleRetry = () => {
    if (pendingConfig) handleChange(pendingConfig);
  };

  if (stage !== "user_review") {
    return (
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">Session config — read only</span>
          <span className="text-xs text-gray-500">🔒 locked at this stage</span>
        </div>
        <FeaturizerConfigEditor value={featurizerConfig} readOnly />
        <p className="text-xs text-gray-500">Editable only during the review step.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">Session config — editable while in review</span>
        {status === "saving" && <span className="text-xs text-gray-400">Saving…</span>}
        {status === "saved" && <span className="text-xs text-green-600">✓ Saved</span>}
        {status === "failed" && (
          <span className="text-xs text-red-500 flex items-center gap-2">
            Failed to save
            <button onClick={handleRetry} className="underline underline-offset-2">
              retry
            </button>
          </span>
        )}
      </div>
      <FeaturizerConfigEditor value={featurizerConfig} onChange={handleChange} />
    </div>
  );
}
