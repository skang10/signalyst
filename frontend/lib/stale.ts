import type { PendingSource } from "./api";

export function isSessionStale(
  session: {
    timeframeStart: string | null;
    timeframeEnd: string | null;
    pendingSources: PendingSource[];
  },
  latestArtifact: {
    data_manifest: {
      date_range: { start: string; end: string };
      requested_start?: string;
      requested_end?: string;
    };
    sources: { connector_id: string }[];
  } | null,
): boolean {
  if (!latestArtifact) return false;

  const artifactStart =
    latestArtifact.data_manifest.requested_start ?? latestArtifact.data_manifest.date_range.start;
  const artifactEnd =
    latestArtifact.data_manifest.requested_end ?? latestArtifact.data_manifest.date_range.end;

  const tfChanged =
    session.timeframeStart !== artifactStart || session.timeframeEnd !== artifactEnd;

  const sessionIds = session.pendingSources
    .map((s) => s.connector_id)
    .sort()
    .join(",");
  const artifactIds = latestArtifact.sources
    .map((s) => s.connector_id)
    .sort()
    .join(",");
  const sourcesChanged = sessionIds !== artifactIds;

  return tfChanged || sourcesChanged;
}
