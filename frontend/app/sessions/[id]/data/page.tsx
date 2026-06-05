"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import type { DataArtifactDetail } from "@/lib/api";

function MetricCard({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`flex-1 px-3 py-2 rounded border bg-[#111827] ${warn ? "border-[#f59e0b]" : "border-[#21262d]"}`}
    >
      <div className="text-[10px] text-[#6b7280] uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-mono ${warn ? "text-[#f59e0b]" : "text-[#f9fafb]"}`}>
        {value}
      </div>
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs === 0) return "0";
  if (abs >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (abs >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}

function DataSnapshotTable({
  seriesPreview,
  missingPct,
}: {
  seriesPreview: Record<string, { date: string; value: number | null }[]>;
  missingPct: Record<string, number>;
}) {
  const [showAll, setShowAll] = useState(false);
  const tickers = Object.keys(seriesPreview);

  // Build date-aligned rows from all series
  const dateMap = new Map<string, Record<string, number | null>>();
  for (const [ticker, points] of Object.entries(seriesPreview)) {
    for (const { date, value } of points) {
      if (!dateMap.has(date)) dateMap.set(date, {});
      dateMap.get(date)![ticker] = value;
    }
  }
  const allDates = Array.from(dateMap.keys()).sort();
  const PREVIEW_ROWS = 5;
  const displayDates = showAll ? allDates : allDates.slice(-PREVIEW_ROWS);

  if (tickers.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#4b5563] uppercase tracking-wider">Snapshot</span>
        <button
          onClick={() => setShowAll((s) => !s)}
          className="text-xs text-[#4b5563] hover:text-[#9ca3af] transition-colors"
        >
          {showAll ? `Show last ${PREVIEW_ROWS}` : `Show all ${allDates.length} rows`}
        </button>
      </div>
      <div className="overflow-auto rounded border border-[#21262d]">
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-[#111827] border-b border-[#21262d]">
              <th className="text-left px-3 py-2 text-[#4b5563] font-normal whitespace-nowrap">Date</th>
              {tickers.map((ticker) => (
                <th key={ticker} className="text-right px-3 py-2 font-normal whitespace-nowrap">
                  <span className="text-[#9ca3af]">{ticker}</span>
                  {(missingPct[ticker] ?? 0) > 0 && (
                    <span className="ml-1 text-[#f59e0b]">·{missingPct[ticker]}%</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayDates.map((date, i) => {
              const row = dateMap.get(date) ?? {};
              return (
                <tr
                  key={date}
                  className={`border-b border-[#1f2937] last:border-0 ${
                    i % 2 === 0 ? "bg-[#0d1117]" : "bg-[#111827]"
                  }`}
                >
                  <td className="px-3 py-1.5 text-[#6b7280]">{date}</td>
                  {tickers.map((ticker) => {
                    const v = row[ticker];
                    return (
                      <td
                        key={ticker}
                        className={`px-3 py-1.5 text-right ${
                          v == null ? "text-[#374151]" : "text-[#f9fafb]"
                        }`}
                      >
                        {fmt(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Sparkline({ points }: { points: { date: string; value: number | null }[] }) {
  const values = points.map((p) => p.value ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 300;
  const height = 48;
  const pts = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-12">
      <polyline points={pts} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
    </svg>
  );
}

type FilePreview = { start: string; end: string; rows: number; columns: string[] } | null;

function parseCsvPreview(text: string): FilePreview {
  const lines = text.split("\n").filter((l) => l.trim());
  if (lines.length < 2) return null;
  const header = lines[0].split(",").map((h) => h.trim().replace(/"/g, ""));
  const dataLines = lines.slice(1).filter((l) => l.trim());
  if (dataLines.length === 0) return null;

  const firstRow = dataLines[0].split(",");
  const lastRow = dataLines[dataLines.length - 1].split(",");
  const start = (firstRow[0] ?? "").trim().replace(/"/g, "");
  const end = (lastRow[0] ?? "").trim().replace(/"/g, "");
  return { start, end, rows: dataLines.length, columns: header.slice(1) };
}

function UploadPanel({
  sessionId,
  compact,
  onSuccess,
  existingDateRange,
}: {
  sessionId: string;
  compact?: boolean;
  onSuccess?: (artifactId: string) => void;
  existingDateRange?: { start: string; end: string } | null;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<FilePreview>(null);
  const [sourceName, setSourceName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setPreview(null);
    // Only preview CSV — parquet not readable as text
    if (f.name.endsWith(".csv")) {
      // Read just enough bytes for header + first/last rows
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = (e.target?.result as string) ?? "";
        setPreview(parseCsvPreview(text));
      };
      reader.readAsText(f.slice(0, 64_000)); // first 64 KB is enough for preview
    }
  };

  // Check if uploaded date range overlaps with existing
  const overlapWarning: string | null = (() => {
    if (!preview || !existingDateRange) return null;
    const uploadStart = new Date(preview.start);
    const uploadEnd = new Date(preview.end);
    const existStart = new Date(existingDateRange.start);
    const existEnd = new Date(existingDateRange.end);
    if (isNaN(uploadStart.getTime()) || isNaN(existStart.getTime())) return null;
    if (uploadEnd < existStart || uploadStart > existEnd) {
      return `No date overlap: your file covers ${preview.start} – ${preview.end}, existing data covers ${existingDateRange.start} – ${existingDateRange.end}. Merging will produce ~50% missing values.`;
    }
    return null;
  })();

  const handleUpload = async (mode: "merge" | "replace" = "merge") => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const { artifact_id } = await api.uploadData(sessionId, file, sourceName || file.name, mode);
      onSuccess?.(artifact_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const inner = (
    <div className={`w-full ${compact ? "" : "max-w-md"} flex flex-col gap-4`}>
      {!compact && (
        <p className="text-sm text-[#9ca3af] text-center">
          Upload a CSV or Parquet file to merge with existing data.
        </p>
      )}

        {/* Drop zone */}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="w-full border-2 border-dashed border-[#21262d] hover:border-[#3b82f6] rounded-lg p-8 flex flex-col items-center gap-2 text-[#6b7280] hover:text-[#9ca3af] transition-colors"
        >
          <span className="text-3xl">↑</span>
          <span className="text-sm">{file ? file.name : "Click to choose file"}</span>
          <span className="text-xs">CSV or Parquet · max 50 MB</span>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.parquet"
          className="hidden"
          onChange={(e) => handleFileChange(e.target.files?.[0])}
        />

        {/* File preview */}
        {preview && (
          <div className="bg-[#0d1117] border border-[#21262d] rounded p-3 flex flex-col gap-1 text-xs">
            <div className="flex gap-4 text-[#9ca3af]">
              <span>{preview.rows} rows</span>
              <span>{preview.columns.length} columns</span>
              <span>{preview.start} – {preview.end}</span>
            </div>
            <div className="text-[#6b7280] font-mono truncate">
              {preview.columns.slice(0, 6).join(", ")}{preview.columns.length > 6 ? ` +${preview.columns.length - 6} more` : ""}
            </div>
          </div>
        )}

        {/* Overlap warning */}
        {overlapWarning && (
          <div className="flex gap-2 bg-[#1c1208] border border-[#f59e0b] rounded p-3 text-xs text-[#f59e0b]">
            <span>⚠</span>
            <span>{overlapWarning}</span>
          </div>
        )}

        {/* Source name */}
        <input
          type="text"
          value={sourceName}
          onChange={(e) => setSourceName(e.target.value)}
          placeholder="Source name (optional)"
          className="w-full bg-[#111827] border border-[#21262d] rounded px-3 py-2 text-sm text-[#f9fafb] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6]"
        />

        {error && <p className="text-xs text-[#ef4444]">{error}</p>}

        {/* Action buttons — context-aware based on overlap */}
        {overlapWarning ? (
          // No overlap: recommend Replace; Merge is secondary
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleUpload("replace")}
              disabled={!file || uploading}
              className="w-full py-2 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {uploading ? "Uploading…" : "Replace existing data with this file"}
            </button>
            <button
              onClick={() => handleUpload("merge")}
              disabled={!file || uploading}
              className="w-full py-1.5 rounded border border-[#374151] text-[#9ca3af] hover:text-[#f9fafb] text-xs transition-colors disabled:opacity-40"
            >
              Merge anyway (will create gaps)
            </button>
          </div>
        ) : existingDateRange ? (
          // Overlap exists: Merge is primary; Replace is secondary
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleUpload("merge")}
              disabled={!file || uploading}
              className="w-full py-2 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {uploading ? "Uploading…" : "Merge with existing data"}
            </button>
            <button
              onClick={() => handleUpload("replace")}
              disabled={!file || uploading}
              className="w-full py-1.5 rounded border border-[#374151] text-[#9ca3af] hover:text-[#f9fafb] text-xs transition-colors disabled:opacity-40"
            >
              Replace existing data
            </button>
          </div>
        ) : (
          // No existing data: single upload button
          <button
            onClick={() => handleUpload("replace")}
            disabled={!file || uploading}
            className="w-full py-2 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        )}
      </div>
  );

  if (compact) return inner;
  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
      {inner}
    </div>
  );
}

const MISSING_PCT_LIMIT = 30;

export default function DataPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, stage, setSession } = useSessionStore();
  const [artifact, setArtifact] = useState<DataArtifactDetail | null>(null);
  const [fetchedId, setFetchedId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [proceeding, setProceeding] = useState(false);
  const [proceedError, setProceedError] = useState<string | null>(null);

  // Fetch artifact detail whenever the store's artifact list changes
  useEffect(() => {
    if (!id || artifacts.data.length === 0) return;
    const latestRef = artifacts.data[artifacts.data.length - 1];
    if (latestRef.artifact_id === fetchedId) return;
    setFetchError(null);
    api
      .getArtifact(id, latestRef.artifact_id)
      .then((data) => {
        setArtifact(data);
        setFetchedId(latestRef.artifact_id);
      })
      .catch((e: unknown) => {
        setFetchError(e instanceof Error ? e.message : "Failed to load artifact");
      });
  }, [id, artifacts.data, fetchedId]);

  const handleProceed = async () => {
    if (!id) return;
    setProceeding(true);
    setProceedError(null);
    try {
      await api.proceed(id);
      const updated = await api.getSession(id);
      setSession(updated);
    } catch (e) {
      setProceedError(e instanceof Error ? e.message : "Failed to start analysis");
    } finally {
      setProceeding(false);
    }
  };

  // Called by UploadPanel with the artifact_id returned by the API
  const handleUploadSuccess = async (artifactId: string) => {
    if (!id) return;
    try {
      // Fetch artifact detail directly — don't rely on store chain
      const [detail, updated] = await Promise.all([
        api.getArtifact(id, artifactId),
        api.getSession(id),
      ]);
      setSession(updated);   // sync the rest of the session state
      setArtifact(detail);
      setFetchedId(artifactId);
      setFetchError(null);
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Failed to load uploaded data");
    }
  };

  if (artifacts.data.length === 0) {
    return <UploadPanel sessionId={id} onSuccess={handleUploadSuccess} />;
  }

  if (fetchError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2">
        <p className="text-[#ef4444] text-sm">{fetchError}</p>
        <button
          onClick={() => { setFetchedId(null); setFetchError(null); }}
          className="text-xs text-[#9ca3af] underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        Loading…
      </div>
    );
  }

  const dm = artifact.data_manifest;
  const missingValues = Object.values(dm.missing_pct);
  const avgMissing =
    missingValues.length > 0
      ? missingValues.reduce((s, v) => s + v, 0) / missingValues.length
      : 0;

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-[#f9fafb]">Data Manifest</h2>
        {artifact.cache_hit && <span className="text-xs text-[#f59e0b]">⚡ Cached</span>}
      </div>

      <div className="flex gap-2">
        <MetricCard label="Rows" value={String(dm.rows)} />
        <MetricCard label="Signals" value={String(dm.tickers.length)} />
        <MetricCard label="Date range" value={`${dm.date_range.start} – ${dm.date_range.end}`} />
        <MetricCard label="Avg missing" value={`${avgMissing.toFixed(1)}%`} warn={avgMissing > 1} />
      </div>

      <DataSnapshotTable seriesPreview={artifact.series_preview} missingPct={dm.missing_pct} />

      {/* Run Analysis — only shown at USER_REVIEW */}
      {stage === "user_review" && (
        <div className="flex flex-col gap-2">
          {avgMissing > MISSING_PCT_LIMIT ? (
            <div className="flex items-start gap-3 bg-[#1c1208] border border-[#f59e0b] rounded p-3">
              <span className="text-[#f59e0b] mt-0.5">⚠</span>
              <div className="flex-1">
                <p className="text-sm text-[#f59e0b] font-medium">
                  {avgMissing.toFixed(1)}% average missing data — analysis blocked
                </p>
                <p className="text-xs text-[#9ca3af] mt-1">
                  More than {MISSING_PCT_LIMIT}% missing values will produce unreliable results.
                  Upload a file that overlaps the existing date range, or use
                  &ldquo;Replace existing data&rdquo; to start fresh.
                </p>
              </div>
            </div>
          ) : (
            <button
              onClick={handleProceed}
              disabled={proceeding}
              className="w-full py-2.5 rounded bg-[#15803d] hover:bg-[#16a34a] text-white text-sm font-semibold transition-colors disabled:opacity-40"
            >
              {proceeding ? "Starting analysis…" : "Run Analysis →"}
            </button>
          )}
          {proceedError && (
            <p className="text-xs text-[#ef4444]">{proceedError}</p>
          )}
        </div>
      )}

      {/* Backend warnings (date overlap, WTI hint, etc.) */}
      {dm.warnings?.length ? (
        <div className="flex flex-col gap-1">
          {dm.warnings.map((w, i) => (
            <div key={i} className="flex gap-2 bg-[#1c1208] border border-[#f59e0b] rounded p-2 text-xs text-[#f59e0b]">
              <span>⚠</span><span>{w}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {Object.entries(artifact.series_preview).map(([ticker, points]) => {
          const stats = dm.summary_stats[ticker];
          return (
            <div key={ticker} className="bg-[#111827] rounded border border-[#21262d] p-3">
              <div className="text-xs font-mono text-[#9ca3af] mb-2">{ticker}</div>
              <Sparkline points={points} />
              {stats && (
                <div className="flex gap-3 mt-2 text-[10px] text-[#6b7280] font-mono">
                  <span>min {stats.min.toFixed(2)}</span>
                  <span>mean {stats.mean.toFixed(2)}</span>
                  <span>max {stats.max.toFixed(2)}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <UploadSection
        sessionId={id}
        onSuccess={handleUploadSuccess}
        existingDateRange={dm.date_range}
      />
    </div>
  );
}

function UploadSection({
  sessionId,
  onSuccess,
  existingDateRange,
}: {
  sessionId: string;
  onSuccess: (artifactId: string) => void;
  existingDateRange?: { start: string; end: string };
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-[#21262d] rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#9ca3af] hover:text-[#f9fafb] transition-colors"
      >
        <span>Upload additional data</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-[#21262d] p-4">
          <UploadPanel
            sessionId={sessionId}
            compact
            onSuccess={onSuccess}
            existingDateRange={existingDateRange}
          />
        </div>
      )}
    </div>
  );
}
