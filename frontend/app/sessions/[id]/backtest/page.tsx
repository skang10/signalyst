"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BacktestTab } from "@/components/tabs/BacktestTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { DataArtifactDetail } from "@/lib/api";

export default function BacktestPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <BacktestTab backtest={null} />
      </div>
    </div>
  );
}
