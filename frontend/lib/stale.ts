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

  const { requested_start: artifactStart, requested_end: artifactEnd } =
    latestArtifact.data_manifest;

  // Only compare timeframe when the artifact has the requested dates stamped on it.
  // Older artifacts lack this field; falling back to date_range (actual data dates) would
  // produce false positives because trading calendars shift the start by a day or two.
  const tfChanged =
    artifactStart !== undefined && artifactEnd !== undefined
      ? session.timeframeStart !== artifactStart || session.timeframeEnd !== artifactEnd
      : false;

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
