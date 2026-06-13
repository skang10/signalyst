import type { PendingSource } from "./api";

// Normalizes a source's params so order differences (e.g. ticker order) don't
// register as a change, then serializes for comparison.
function normalizeSource(source: PendingSource): string {
  const params = source.params ?? {};
  const tickers = params.tickers;
  const normalizedParams = Array.isArray(tickers)
    ? { ...params, tickers: [...tickers].sort() }
    : params;
  return JSON.stringify({ connector_id: source.connector_id, params: normalizedParams });
}

function normalizeSources(sources: PendingSource[]): string {
  return sources.map(normalizeSource).sort().join("|");
}

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
    sources: PendingSource[];
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

  const sourcesChanged =
    normalizeSources(session.pendingSources) !== normalizeSources(latestArtifact.sources);

  return tfChanged || sourcesChanged;
}
