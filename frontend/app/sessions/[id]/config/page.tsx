"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { ConnectorEditor } from "@/components/ConnectorEditor";
import { UploadRow } from "@/components/UploadDataPanel";
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

function SectionLabel({
  children,
  open,
  onToggle,
}: {
  children: React.ReactNode;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center gap-1.5 text-[10px] font-semibold tracking-widest text-gray-400 uppercase mb-2 hover:text-gray-600 transition-colors"
    >
      <span>{open ? "▾" : "▸"}</span>
      {children}
    </button>
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
function ConfigForm({
  session,
  onSessionUpdated,
}: {
  session: Session;
  onSessionUpdated: (s: Session) => void;
}) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { stage, status, setSession } = useSessionStore();
  const { artifacts } = useSessionStore();

  const [connectors, setConnectors] = useState<ConnectorOut[]>([]);
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  const [localStart, setLocalStart] = useState(session.timeframe_start ?? "");
  const [localEnd, setLocalEnd] = useState(session.timeframe_end ?? "");
  const [localSources, setLocalSources] = useState<PendingSource[]>(session.pending_sources ?? []);

  const [localFeatConfig, setLocalFeatConfig] = useState<FeaturizerConfig>(
    session.featurizer_config as FeaturizerConfig,
  );
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  const [sessionOpen, setSessionOpen] = useState(true);
  const [connectorsOpen, setConnectorsOpen] = useState(true);
  const [featurizerOpen, setFeaturizerOpen] = useState(true);

  useEffect(() => {
    // SPEC-type connectors have no data-fetching implementation yet (see CLAUDE.md) —
    // hide them so users aren't misled into selecting a source that fetches nothing.
    api
      .getConnectors()
      .then((cs) => setConnectors(cs.filter((c) => c.type !== "spec")))
      .catch(() => {});
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

  const isDirty =
    localStart !== (session.timeframe_start ?? "") ||
    localEnd !== (session.timeframe_end ?? "") ||
    JSON.stringify(localSources) !== JSON.stringify(session.pending_sources ?? []) ||
    JSON.stringify(localFeatConfig) !== JSON.stringify(session.featurizer_config);

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
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  const isRunning = status === "running";

  const handleSave = async () => {
    if (!id) return;
    setSaveStatus("saving");
    try {
      await api.updateConfig(id, {
        timeframe_start: localStart,
        timeframe_end: localEnd,
        pending_sources: localSources,
        featurizer_config_patch: localFeatConfig,
      });
      const updated = await api.getSession(id);
      setSession(updated);
      onSessionUpdated(updated);
      setLocalStart(updated.timeframe_start ?? "");
      setLocalEnd(updated.timeframe_end ?? "");
      setLocalSources(updated.pending_sources ?? []);
      setLocalFeatConfig(updated.featurizer_config as FeaturizerConfig);
      setSaveStatus("saved");
    } catch {
      setSaveStatus("failed");
    }
  };

  const handleDiscard = () => {
    setLocalStart(session.timeframe_start ?? "");
    setLocalEnd(session.timeframe_end ?? "");
    setLocalSources(session.pending_sources ?? []);
    setLocalFeatConfig(session.featurizer_config as FeaturizerConfig);
  };

  const handleRerun = async () => {
    if (!id) return;
    await api.rerun(id, "data_gathering");
    const updated = await api.getSession(id);
    setSession(updated);
    router.push(`/sessions/${id}/activity`);
  };

  const handleUploadSuccess = async (artifactId: string) => {
    if (!id) return;
    const [detail, updated] = await Promise.all([
      api.getArtifact(id, artifactId),
      api.getSession(id),
    ]);
    setSession(updated);
    setLatestArtifact(detail);
    setLocalSources(updated.pending_sources ?? []);
    onSessionUpdated(updated);
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
            className="ml-auto text-brand underline underline-offset-2 whitespace-nowrap"
          >
            Re-run from data →
          </button>
        </div>
      )}

      {(isDirty || saveStatus !== "idle") && (
        <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg flex-shrink-0">
          <span className="text-xs text-gray-500">You have unsaved changes.</span>
          <div className="flex items-center gap-3">
            <SaveIndicator status={saveStatus} onRetry={handleSave} />
            {isDirty && (
              <button
                onClick={handleDiscard}
                disabled={isRunning || saveStatus === "saving"}
                className="px-3 py-1 text-xs font-medium text-gray-500 rounded hover:bg-gray-100 disabled:opacity-40 transition-colors"
              >
                Discard
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={isRunning || saveStatus === "saving"}
              className="px-3 py-1 text-xs font-medium bg-brand text-white rounded hover:bg-brand-hover disabled:opacity-40 transition-colors"
            >
              {saveStatus === "saving" ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}

      {/* SESSION */}
      <div>
        <SectionLabel open={sessionOpen} onToggle={() => setSessionOpen((v) => !v)}>
          Session
        </SectionLabel>
        {sessionOpen && (
          <div className="border border-gray-200 rounded-lg p-3 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Market profile</span>
              <span className="bg-gray-100 text-gray-700 text-xs font-semibold px-2 py-0.5 rounded">
                {session.market_profile ?? "—"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Timeframe</span>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={localStart}
                  disabled={isRunning}
                  onChange={(e) => setLocalStart(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-brand disabled:opacity-40"
                />
                <span className="text-xs text-gray-400">→</span>
                <input
                  type="date"
                  value={localEnd}
                  disabled={isRunning}
                  onChange={(e) => setLocalEnd(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-brand disabled:opacity-40"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* DATA CONNECTORS */}
      <div>
        <SectionLabel open={connectorsOpen} onToggle={() => setConnectorsOpen((v) => !v)}>
          Data Connectors
        </SectionLabel>
        {connectorsOpen && (
          <ConnectorEditor
            available={connectors}
            value={localSources}
            onChange={setLocalSources}
            readOnly={isRunning}
            footer={
              <UploadRow
                sessionId={id}
                onSuccess={handleUploadSuccess}
                existingDateRange={latestArtifact?.data_manifest.date_range}
              />
            }
          />
        )}
      </div>

      {/* FEATURIZER */}
      <div>
        <SectionLabel open={featurizerOpen} onToggle={() => setFeaturizerOpen((v) => !v)}>
          Featurizer
        </SectionLabel>
        {featurizerOpen && (
          <>
            <div className="border border-gray-200 rounded-lg p-3">
              <FeaturizerConfigEditor
                value={localFeatConfig}
                onChange={stage === "user_review" ? setLocalFeatConfig : undefined}
                readOnly={stage !== "user_review"}
              />
            </div>
            {stage !== "user_review" && (
              <p className="text-xs text-gray-400 mt-2">Editable only during the review step.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const [session, setSessionLocal] = useState<Session | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getSession(id).then(setSessionLocal).catch(() => {});
  }, [id]);

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return <ConfigForm session={session} onSessionUpdated={setSessionLocal} />;
}
