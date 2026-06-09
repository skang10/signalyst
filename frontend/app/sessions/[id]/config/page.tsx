"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { ConnectorEditor } from "@/components/ConnectorEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type {
  ConnectorOut,
  DataArtifactDetail,
  FeaturizerConfig,
  PendingSource,
  Session,
} from "@/lib/api";

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

// Rendered only after the session is loaded — useState initializes from correct values.
function ConfigForm({ session }: { session: Session }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { featurizerConfig, stage, status, setSession } = useSessionStore();
  const { artifacts } = useSessionStore();

  const [connectors, setConnectors] = useState<ConnectorOut[]>([]);
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  const [localStart, setLocalStart] = useState(session.timeframe_start ?? "");
  const [localEnd, setLocalEnd] = useState(session.timeframe_end ?? "");
  const [localSources, setLocalSources] = useState<PendingSource[]>(session.pending_sources ?? []);

  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [featStatus, setFeatStatus] = useState<SaveStatus>("idle");
  const [pendingFeatConfig, setPendingFeatConfig] = useState<FeaturizerConfig | null>(null);

  useEffect(() => {
    api.getConnectors().then(setConnectors).catch(() => {});
  }, []);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    if (saveStatus !== "saved") return;
    const t = setTimeout(() => setSaveStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [saveStatus]);

  useEffect(() => {
    if (featStatus !== "saved") return;
    const t = setTimeout(() => setFeatStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [featStatus]);

  const isDirty =
    localStart !== (session.timeframe_start ?? "") ||
    localEnd !== (session.timeframe_end ?? "") ||
    JSON.stringify(localSources) !== JSON.stringify(session.pending_sources ?? []);

  const stale = isSessionStale(
    {
      timeframeStart: session.timeframe_start ?? null,
      timeframeEnd: session.timeframe_end ?? null,
      pendingSources: session.pending_sources ?? [],
    },
    latestArtifact
      ? {
          data_manifest: {
            date_range: latestArtifact.data_manifest.date_range,
            requested_start: latestArtifact.data_manifest.requested_start,
            requested_end: latestArtifact.data_manifest.requested_end,
          },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  const isRunning = status === "running";

  const handleSaveConfig = async () => {
    if (!id) return;
    setSaveStatus("saving");
    try {
      await api.updateConfig(id, {
        timeframe_start: localStart,
        timeframe_end: localEnd,
        pending_sources: localSources,
      });
      const updated = await api.getSession(id);
      setSession(updated);
      // Explicitly reset local state to match what was saved
      setLocalStart(updated.timeframe_start ?? "");
      setLocalEnd(updated.timeframe_end ?? "");
      setLocalSources(updated.pending_sources ?? []);
      setSaveStatus("saved");
    } catch {
      setSaveStatus("failed");
    }
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

      {(isDirty || saveStatus !== "idle") && (
        <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg flex-shrink-0">
          <span className="text-xs text-gray-500">You have unsaved changes.</span>
          <div className="flex items-center gap-3">
            <SaveIndicator status={saveStatus} onRetry={handleSaveConfig} />
            <button
              onClick={handleSaveConfig}
              disabled={isRunning || saveStatus === "saving"}
              className="px-3 py-1 text-xs font-medium bg-teal-600 text-white rounded hover:bg-teal-700 disabled:opacity-40 transition-colors"
            >
              {saveStatus === "saving" ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}

      {/* SESSION */}
      <div>
        <SectionLabel>Session</SectionLabel>
        <div className="border border-gray-200 rounded-lg p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Market profile</span>
            <span className="bg-gray-100 text-gray-700 text-xs font-semibold px-2 py-0.5 rounded">
              {session.market_profile ?? "—"}
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
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
              <span className="text-xs text-gray-400">→</span>
              <input
                type="date"
                value={localEnd}
                disabled={isRunning}
                onChange={(e) => setLocalEnd(e.target.value)}
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
            </div>
          </div>
        </div>
      </div>

      {/* DATA SOURCES */}
      <div>
        <SectionLabel>Data Sources</SectionLabel>
        <ConnectorEditor
          available={connectors}
          value={localSources}
          onChange={setLocalSources}
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
          value={featurizerConfig!}
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

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const { featurizerConfig } = useSessionStore();
  const [session, setSessionLocal] = useState<Session | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getSession(id).then(setSessionLocal).catch(() => {});
  }, [id]);

  if (!featurizerConfig || !session) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return <ConfigForm session={session} />;
}
