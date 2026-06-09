import type { PendingSource } from "./api";

export function isSessionStale(
  session: {
    timeframeStart: string | null;
    timeframeEnd: string | null;
    pendingSources: PendingSource[];
  },
  latestArtifact: {
    data_manifest: { date_range: { start: string; end: string } };
    sources: { connector_id: string }[];
  } | null,
): boolean {
  if (!latestArtifact) return false;

  const tfChanged =
    session.timeframeStart !== latestArtifact.data_manifest.date_range.start ||
    session.timeframeEnd !== latestArtifact.data_manifest.date_range.end;

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
