"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MarketSnapshot } from "@/lib/api";

function IndicatorCard({
  label,
  value,
  changePct,
  warn,
}: {
  label: string;
  value: string;
  changePct: number | null;
  warn?: boolean;
}) {
  const changeColor =
    changePct === null
      ? "text-[#6b7280]"
      : changePct >= 0
        ? "text-[#22c55e]"
        : "text-[#ef4444]";

  return (
    <div
      className={[
        "flex-1 px-3 py-2 rounded border bg-[#111827]",
        warn ? "border-[#f59e0b]" : "border-[#21262d]",
      ].join(" ")}
    >
      <div className="text-[10px] text-[#6b7280] uppercase tracking-wider mb-1">{label}</div>
      <div className="text-base font-mono text-[#f9fafb]">{value}</div>
      {changePct !== null && (
        <div className={`text-xs ${changeColor}`}>
          {changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

export function SessionIndicators() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);

  useEffect(() => {
    api.getMarketSnapshot().then(setSnapshot).catch(() => {});
  }, []);

  return (
    <div className="flex gap-2 px-4 py-3 border-b border-[#21262d]">
      <IndicatorCard
        label="WTI Crude"
        value={snapshot?.wti ? `$${snapshot.wti.price.toFixed(2)}` : "—"}
        changePct={snapshot?.wti?.change_pct ?? null}
      />
      <IndicatorCard
        label="Brent"
        value={snapshot?.brent ? `$${snapshot.brent.price.toFixed(2)}` : "—"}
        changePct={snapshot?.brent?.change_pct ?? null}
      />
      <IndicatorCard
        label="DXY"
        value={snapshot?.dxy ? snapshot.dxy.price.toFixed(1) : "—"}
        changePct={snapshot?.dxy?.change_pct ?? null}
      />
      <IndicatorCard
        label="GPR Index"
        value={snapshot?.gpr ? snapshot.gpr.value.toFixed(1) : "—"}
        changePct={snapshot?.gpr?.change_pct ?? null}
        warn={(snapshot?.gpr?.value ?? 0) > 200}
      />
    </div>
  );
}
