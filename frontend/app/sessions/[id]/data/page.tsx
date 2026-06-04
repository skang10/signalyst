"use client";

import { useEffect, useState } from "react";
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

export default function DataPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts } = useSessionStore();
  const [artifact, setArtifact] = useState<DataArtifactDetail | null>(null);
  const [fetchedId, setFetchedId] = useState<string | null>(null);

  useEffect(() => {
    if (!id || artifacts.data.length === 0) return;
    const latestRef = artifacts.data[artifacts.data.length - 1];
    if (latestRef.artifact_id === fetchedId) return;
    api
      .getArtifact(id, latestRef.artifact_id)
      .then((data) => {
        setArtifact(data);
        setFetchedId(latestRef.artifact_id);
      })
      .catch(() => {});
  }, [id, artifacts.data, fetchedId]);

  if (artifacts.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        No data yet — upload a CSV or Parquet file to populate this view
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
        <MetricCard label="Series" value={String(dm.tickers.length)} />
        <MetricCard label="Missing %" value={`${avgMissing.toFixed(1)}%`} warn={avgMissing > 1} />
      </div>

      <div className="flex flex-wrap gap-2">
        {dm.tickers.map((ticker) => (
          <span
            key={ticker}
            className={`text-xs px-2 py-0.5 rounded border ${
              (dm.missing_pct[ticker] ?? 0) > 1
                ? "border-[#f59e0b] text-[#f59e0b]"
                : "border-[#21262d] text-[#9ca3af]"
            }`}
          >
            {ticker}
            {dm.missing_pct[ticker] !== undefined && ` · ${dm.missing_pct[ticker]}% missing`}
          </span>
        ))}
      </div>

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
    </div>
  );
}
