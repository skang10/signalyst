"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { ConnectorEditor } from "@/components/ConnectorEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { ConnectorOut, DataArtifactDetail, FeaturizerConfig, PendingSource } from "@/lib/api";

type SaveStatus = "idle" | "saving" | "saved" | "failed";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold tracking-widest text-gray-400 uppercase mb-2">
      {children}
    </div>
  );
}

function SaveIndicator({ status, onRetry }: { status: SaveStatus; onRetry: () => void }) {
  if (status === "idle") return null;
  if (status === "saving") return <span className="text-xs text-gray-400">Saving…</span>;
  if (status === "saved") return <span className="text-xs text-green-600">✓ Saved</span>;
  return (
    <span className="text-xs text-red-500 flex items-center gap-2">
      Failed
      <button onClick={onRetry} className="underline underline-offset-2">
        retry
      </button>
    </span>
  );
}

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const {
    featurizerConfig,
    stage,
    status,
    marketProfile,
    timeframeStart,
    timeframeEnd,
    pendingSources,
    artifacts,
    setSession,
  } = useSessionStore();

  const [connectors, setConnectors] = useState<ConnectorOut[]>([]);
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  const [localStart, setLocalStart] = useState(timeframeStart ?? "");
  const [localEnd, setLocalEnd] = useState(timeframeEnd ?? "");
  const [localSources, setLocalSources] = useState<PendingSource[]>(pendingSources);

  const [tfStatus, setTfStatus] = useState<SaveStatus>("idle");
  const [srcStatus, setSrcStatus] = useState<SaveStatus>("idle");
  const [featStatus, setFeatStatus] = useState<SaveStatus>("idle");
  const [pendingFeatConfig, setPendingFeatConfig] = useState<FeaturizerConfig | null>(null);

  const srcDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync local copies when store updates (e.g. after session refresh in layout)
  useEffect(() => setLocalStart(timeframeStart ?? ""), [timeframeStart]);
  useEffect(() => setLocalEnd(timeframeEnd ?? ""), [timeframeEnd]);
  useEffect(() => setLocalSources(pendingSources), [pendingSources]);

  useEffect(() => {
    api.getConnectors().then(setConnectors).catch(() => {});
  }, []);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  // Auto-clear save indicators after 2 s
  useEffect(() => {
    if (tfStatus !== "saved") return;
    const t = setTimeout(() => setTfStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [tfStatus]);
  useEffect(() => {
    if (srcStatus !== "saved") return;
    const t = setTimeout(() => setSrcStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [srcStatus]);
  useEffect(() => {
    if (featStatus !== "saved") return;
    const t = setTimeout(() => setFeatStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [featStatus]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  const isRunning = status === "running";

  const saveTimeframe = useCallback(async () => {
    if (!id) return;
    setTfStatus("saving");
    try {
      await api.updateConfig(id, { timeframe_start: localStart, timeframe_end: localEnd });
      const updated = await api.getSession(id);
      setSession(updated);
      setTfStatus("saved");
    } catch {
      setTfStatus("failed");
    }
  }, [id, localStart, localEnd, setSession]);

  const handleSourcesChange = (next: PendingSource[]) => {
    setLocalSources(next);
    if (srcDebounce.current) clearTimeout(srcDebounce.current);
    srcDebounce.current = setTimeout(async () => {
      if (!id) return;
      setSrcStatus("saving");
      try {
        await api.updateConfig(id, { pending_sources: next });
        const updated = await api.getSession(id);
        setSession(updated);
        setSrcStatus("saved");
      } catch {
        setSrcStatus("failed");
      }
    }, 600);
  };

  const handleFeatChange = async (next: FeaturizerConfig) => {
    if (!id) return;
    setFeatStatus("saving");
    setPendingFeatConfig(next);
    try {
      await api.updateConfig(id, { featurizer_config_patch: next });
      const updated = await api.getSession(id);
      setSession(updated);
      setFeatStatus("saved");
      setPendingFeatConfig(null);
    } catch {
      setFeatStatus("failed");
    }
  };

  const handleRerun = async () => {
    if (!id) return;
    await api.rerun(id, "data_gathering");
    router.push(`/sessions/${id}/activity`);
  };

  if (!featurizerConfig) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {stale && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs flex-shrink-0">
          <span className="text-amber-600">⚠</span>
          <span className="text-amber-700">
            Timeframe or sources changed — results shown are from prior run.
          </span>
          <button
            onClick={handleRerun}
            className="ml-auto text-teal-600 underline underline-offset-2 whitespace-nowrap"
          >
            Re-run from data →
          </button>
        </div>
      )}

      {/* SESSION */}
      <div>
        <SectionLabel>Session</SectionLabel>
        <div className="border border-gray-200 rounded-lg p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Market profile</span>
            <span className="bg-gray-100 text-gray-700 text-xs font-semibold px-2 py-0.5 rounded">
              {marketProfile ?? "—"}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-gray-500">Timeframe</span>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={localStart}
                disabled={isRunning}
                onChange={(e) => setLocalStart(e.target.value)}
                onBlur={saveTimeframe}
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
              <span className="text-xs text-gray-400">→</span>
              <input
                type="date"
                value={localEnd}
                disabled={isRunning}
                onChange={(e) => setLocalEnd(e.target.value)}
                onBlur={saveTimeframe}
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
              <SaveIndicator status={tfStatus} onRetry={saveTimeframe} />
            </div>
          </div>
        </div>
      </div>

      {/* DATA SOURCES */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Data Sources</SectionLabel>
          <SaveIndicator
            status={srcStatus}
            onRetry={() => handleSourcesChange(localSources)}
          />
        </div>
        <ConnectorEditor
          available={connectors}
          value={localSources}
          onChange={handleSourcesChange}
          readOnly={isRunning}
        />
      </div>

      {/* FEATURIZER */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Featurizer</SectionLabel>
          <SaveIndicator
            status={featStatus}
            onRetry={() => pendingFeatConfig && handleFeatChange(pendingFeatConfig)}
          />
        </div>
        <FeaturizerConfigEditor
          value={featurizerConfig}
          onChange={stage === "user_review" ? handleFeatChange : undefined}
          readOnly={stage !== "user_review"}
        />
        {stage !== "user_review" && (
          <p className="text-xs text-gray-400 mt-2">Editable only during the review step.</p>
        )}
      </div>
    </div>
  );
}
