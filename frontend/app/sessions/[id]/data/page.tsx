"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import { visibleTickers } from "@/lib/sourceTickers";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import type { DataArtifactDetail, PendingSource } from "@/lib/api";

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
      className={`flex-1 px-3 py-2 rounded border bg-white ${warn ? "border-amber-400" : "border-gray-200"}`}
    >
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-mono ${warn ? "text-amber-500" : "text-gray-900"}`}>
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

const PAGE_SIZE = 20;

function DataSnapshotTable({
  seriesPreview,
  missingPct,
}: {
  seriesPreview: Record<string, { date: string; value: number | null }[]>;
  missingPct: Record<string, number>;
}) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
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
  const totalPages = Math.max(1, Math.ceil(allDates.length / PAGE_SIZE));
  const clampedPage = Math.min(page, totalPages - 1);
  const start = clampedPage * PAGE_SIZE;
  const displayDates = allDates.slice(start, start + PAGE_SIZE);

  if (tickers.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-gray-400 uppercase tracking-wider hover:text-gray-600 transition-colors"
        >
          <span>{open ? "▾" : "▸"}</span>
          <span>Snapshot</span>
          <span className="normal-case opacity-60">· {allDates.length} rows</span>
        </button>
        {open && allDates.length > PAGE_SIZE && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              {start + 1}–{Math.min(start + PAGE_SIZE, allDates.length)} of {allDates.length}
            </span>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={clampedPage === 0}
              className="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-30 transition-colors px-1"
            >
              ←
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={clampedPage === totalPages - 1}
              className="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-30 transition-colors px-1"
            >
              →
            </button>
          </div>
        )}
      </div>
      {open && <div className="overflow-auto rounded border border-gray-200">
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2 text-gray-400 font-normal whitespace-nowrap">Date</th>
              {tickers.map((ticker) => (
                <th key={ticker} className="text-right px-3 py-2 font-normal whitespace-nowrap">
                  <span className="text-gray-500">{ticker}</span>
                  {(missingPct[ticker] ?? 0) > 0 && (
                    <span className="ml-1 text-amber-500">·{missingPct[ticker]}%</span>
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
                  className={`border-b border-gray-100 last:border-0 ${
                    i % 2 === 0 ? "bg-white" : "bg-gray-50"
                  }`}
                >
                  <td className="px-3 py-1.5 text-gray-400">{date}</td>
                  {tickers.map((ticker) => {
                    const v = row[ticker];
                    return (
                      <td
                        key={ticker}
                        className={`px-3 py-1.5 text-right ${
                          v == null ? "text-gray-300" : "text-gray-900"
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
      </div>}
    </div>
  );
}

const TICKER_DESCRIPTIONS: Record<string, string> = {
  "CL=F": "WTI Crude Oil Futures (NYMEX)",
  "BZ=F": "Brent Crude Oil Futures (ICE)",
  "DX-Y.NYB": "US Dollar Index (DXY)",
  "INDPRO": "Industrial Production Index (Federal Reserve)",
  "eia_inventory_change": "EIA Weekly Crude Oil Inventory Change (barrels)",
  "GPR": "Geopolitical Risk Index (Caldara & Iacoviello)",
  "^VIX": "CBOE Volatility Index",
  "CPIAUCSL": "Consumer Price Index — All Urban Consumers (BLS)",
  "UNRATE": "US Unemployment Rate (%)",
  "DFF": "Federal Funds Effective Rate (%)",
  "M2SL": "M2 Money Supply (billions USD)",
  "^GSPC": "S&P 500 Index",
  "^TNX": "10-Year Treasury Yield (%)",
  "GC=F": "Gold Futures (COMEX)",
  "NG=F": "Natural Gas Futures (NYMEX)",
};

function Sparkline({ points }: { points: { date: string; value: number | null }[] }) {
  const values = points.map((p) => p.value ?? 0);
  if (values.length === 0) return null;

  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;
  const midVal = (minVal + maxVal) / 2;

  // Layout: leave room for Y-axis labels left, X-axis labels bottom
  const mL = 42; const mR = 4; const mT = 6; const mB = 18;
  const W = 300; const H = 90;
  const cW = W - mL - mR;
  const cH = H - mT - mB;

  const pts = values
    .map((v, i) => {
      const x = mL + (i / Math.max(values.length - 1, 1)) * cW;
      const y = mT + cH - ((v - minVal) / range) * cH;
      return `${x},${y}`;
    })
    .join(" ");

  const firstDate = points[0]?.date ?? "";
  const lastDate = points[points.length - 1]?.date ?? "";

  const yTicks = [
    { val: maxVal, y: mT },
    { val: midVal, y: mT + cH / 2 },
    { val: minVal, y: mT + cH },
  ];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-24">
      {/* Axis lines */}
      <line x1={mL} y1={mT} x2={mL} y2={mT + cH} stroke="#e5e7eb" strokeWidth="1" />
      <line x1={mL} y1={mT + cH} x2={mL + cW} y2={mT + cH} stroke="#e5e7eb" strokeWidth="1" />

      {/* Y-axis ticks */}
      {yTicks.map(({ val, y }) => (
        <g key={y}>
          <line x1={mL - 3} y1={y} x2={mL} y2={y} stroke="#d1d5db" strokeWidth="1" />
          <text x={mL - 5} y={y + 3} textAnchor="end" fontSize="8" fill="#6b7280" fontFamily="monospace">
            {fmt(val)}
          </text>
        </g>
      ))}

      {/* X-axis labels */}
      <text x={mL} y={H - 3} textAnchor="start" fontSize="8" fill="#6b7280" fontFamily="monospace">
        {firstDate}
      </text>
      <text x={mL + cW} y={H - 3} textAnchor="end" fontSize="8" fill="#6b7280" fontFamily="monospace">
        {lastDate}
      </text>

      {/* Data line */}
      <polyline points={pts} fill="none" stroke="var(--color-brand)" strokeWidth="1.5" />
    </svg>
  );
}

const MISSING_PCT_LIMIT = 30;

export default function DataPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, stage, timeframeStart, timeframeEnd, pendingSources } =
    useSessionStore();
  const [artifact, setArtifact] = useState<DataArtifactDetail | null>(null);
  const [fetchedId, setFetchedId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Fetch artifact detail whenever the store's artifact list changes
  useEffect(() => {
    if (!id || artifacts.data.length === 0) return;
    const latestRef = artifacts.data[artifacts.data.length - 1];
    if (latestRef.artifact_id === fetchedId) return;
    api
      .getArtifact(id, latestRef.artifact_id)
      .then((data) => {
        setFetchError(null);
        setArtifact(data);
        setFetchedId(latestRef.artifact_id);
      })
      .catch((e: unknown) => {
        setFetchError(e instanceof Error ? e.message : "Failed to load artifact");
      });
  }, [id, artifacts.data, fetchedId]);

  if (artifacts.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-center">
        <p className="text-sm text-gray-500">No data yet.</p>
        <p className="text-xs text-gray-400">
          Configure data sources and upload data on the{" "}
          <Link href={`/sessions/${id}/config`} className="text-brand underline underline-offset-2">
            Config
          </Link>{" "}
          page.
        </p>
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2">
        <p className="text-red-500 text-sm">{fetchError}</p>
        <button
          onClick={() => { setFetchedId(null); setFetchError(null); }}
          className="text-xs text-gray-400 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  const dm = artifact.data_manifest;
  const visible = new Set(
    visibleTickers(dm.tickers, pendingSources, artifact.sources as PendingSource[]),
  );
  const seriesPreview = Object.fromEntries(
    Object.entries(artifact.series_preview).filter(([t]) => visible.has(t)),
  );
  const missingPct = Object.fromEntries(
    Object.entries(dm.missing_pct).filter(([t]) => visible.has(t)),
  );
  const missingValues = Object.values(missingPct);
  const avgMissing =
    missingValues.length > 0
      ? missingValues.reduce((s, v) => s + v, 0) / missingValues.length
      : 0;

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    {
      data_manifest: {
        date_range: dm.date_range,
        requested_start: dm.requested_start,
        requested_end: dm.requested_end,
      },
      sources: artifact.sources as PendingSource[],
    },
  );

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-gray-900">Data Manifest</h2>
        {artifact.cache_hit && <span className="text-xs text-amber-500">⚡ Cached</span>}
      </div>

      <div className="flex gap-2">
        <MetricCard label="Rows" value={String(dm.rows)} />
        <MetricCard label="Signals" value={String(visible.size)} />
        <MetricCard label="Date range" value={`${dm.date_range.start} – ${dm.date_range.end}`} />
        <MetricCard label="Avg missing" value={`${avgMissing.toFixed(1)}%`} warn={avgMissing > 1} />
      </div>

      <DataSnapshotTable seriesPreview={seriesPreview} missingPct={missingPct} />

      {/* High missing data warning — shown at USER_REVIEW when data quality is poor */}
      {stage === "user_review" && avgMissing > MISSING_PCT_LIMIT && (
        <div className="flex items-start gap-3 bg-amber-50 border border-amber-300 rounded p-3">
          <span className="text-amber-500 mt-0.5">⚠</span>
          <div className="flex-1">
            <p className="text-sm text-amber-600 font-medium">
              {avgMissing.toFixed(1)}% average missing data — analysis blocked
            </p>
            <p className="text-xs text-gray-500 mt-1">
              More than {MISSING_PCT_LIMIT}% missing values will produce unreliable results.
              Upload a file that overlaps the existing date range, or use
              &ldquo;Replace existing data&rdquo; to start fresh.
            </p>
          </div>
        </div>
      )}

      {/* Backend warnings (date overlap, WTI hint, etc.) */}
      {dm.warnings?.length ? (
        <div className="flex flex-col gap-1">
          {dm.warnings.map((w, i) => (
            <div key={i} className="flex gap-2 bg-amber-50 border border-amber-300 rounded p-2 text-xs text-amber-600">
              <span>⚠</span><span>{w}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {Object.entries(seriesPreview).map(([ticker, points]) => {
          const stats = dm.summary_stats[ticker];
          return (
            <div key={ticker} className="bg-white rounded border border-gray-200 p-3 group">
              <div className="flex items-baseline gap-2 mb-1">
                <div className="text-xs font-mono text-gray-500">{ticker}</div>
                {TICKER_DESCRIPTIONS[ticker] && (
                  <div className="text-[10px] text-gray-300 group-hover:text-gray-500 transition-colors truncate">
                    {TICKER_DESCRIPTIONS[ticker]}
                  </div>
                )}
              </div>
              <Sparkline points={points} />
              {stats && (
                <div className="flex gap-3 mt-1 text-[10px] text-gray-400 font-mono">
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
