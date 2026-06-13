"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

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

export function UploadPanel({
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
        <p className="text-sm text-gray-500 text-center">
          Upload a CSV or Parquet file to merge with existing data.
        </p>
      )}

        {/* Drop zone */}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="w-full border-2 border-dashed border-gray-200 hover:border-teal-400 rounded-lg p-8 flex flex-col items-center gap-2 text-gray-500 hover:text-gray-700 transition-colors"
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
          <div className="bg-gray-50 border border-gray-200 rounded p-3 flex flex-col gap-1 text-xs">
            <div className="flex gap-4 text-gray-500">
              <span>{preview.rows} rows</span>
              <span>{preview.columns.length} columns</span>
              <span>{preview.start} – {preview.end}</span>
            </div>
            <div className="text-gray-400 font-mono truncate">
              {preview.columns.slice(0, 6).join(", ")}{preview.columns.length > 6 ? ` +${preview.columns.length - 6} more` : ""}
            </div>
          </div>
        )}

        {/* Overlap warning */}
        {overlapWarning && (
          <div className="flex gap-2 bg-amber-50 border border-amber-300 rounded p-3 text-xs text-amber-600">
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
          className="w-full bg-white border border-gray-200 rounded px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-teal-400"
        />

        {error && <p className="text-xs text-red-500">{error}</p>}

        {/* Action buttons — context-aware based on overlap */}
        {overlapWarning ? (
          // No overlap: recommend Replace; Merge is secondary
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleUpload("replace")}
              disabled={!file || uploading}
              className="w-full py-2 rounded bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {uploading ? "Uploading…" : "Replace existing data with this file"}
            </button>
            <button
              onClick={() => handleUpload("merge")}
              disabled={!file || uploading}
              className="w-full py-1.5 rounded border border-gray-200 text-gray-400 hover:text-gray-700 text-xs transition-colors disabled:opacity-40"
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
              className="w-full py-2 rounded bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {uploading ? "Uploading…" : "Merge with existing data"}
            </button>
            <button
              onClick={() => handleUpload("replace")}
              disabled={!file || uploading}
              className="w-full py-1.5 rounded border border-gray-200 text-gray-400 hover:text-gray-700 text-xs transition-colors disabled:opacity-40"
            >
              Replace existing data
            </button>
          </div>
        ) : (
          // No existing data: single upload button
          <button
            onClick={() => handleUpload("replace")}
            disabled={!file || uploading}
            className="w-full py-2 rounded bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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

export function UploadRow({
  sessionId,
  onSuccess,
  existingDateRange,
}: {
  sessionId: string;
  onSuccess: (artifactId: string) => void;
  existingDateRange?: { start: string; end: string } | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-lg px-3 py-2.5 bg-white">
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-gray-500 whitespace-nowrap">Custom Upload</span>
        <span className="text-xs text-gray-400">Add your own CSV or Parquet data</span>
      </div>
      <div className="mt-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="px-2 py-1 rounded-md border border-dashed border-gray-300 text-xs text-gray-400 hover:border-teal-300 hover:text-teal-600 whitespace-nowrap"
        >
          {open ? "− Hide" : "+ Upload file"}
        </button>
      </div>
      {open && (
        <div className="mt-2.5">
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
