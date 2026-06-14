"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturesTab } from "@/components/tabs/FeaturesTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { AnalysisResultDetail, DataArtifactDetail, PendingSource } from "@/lib/api";

export default function FeaturesPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    const last = artifacts.analysis.at(-1);
    if (!id || !last) return;
    api.getAnalysisArtifact(id, last.artifact_id).then(setLatestAnalysis).catch(() => {});
  }, [id, artifacts.analysis]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <FeaturesTab features={latestAnalysis?.feature_importance ?? null} />
      </div>
    </div>
  );
}
