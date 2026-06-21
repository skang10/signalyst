import type { ReactNode } from "react";

type Props = {
  leading?: ReactNode;
  label: string;
  pct: number;
  value: string;
  barClassName?: string;
};

export function MetricBar({ leading, label, pct, value, barClassName }: Props) {
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      {leading && <div className="w-4 flex items-center justify-end">{leading}</div>}
      <div className="w-32 text-right text-gray-500 truncate">{label}</div>
      <div className="flex-1 bg-gray-100 rounded h-2 overflow-hidden">
        <div
          className={`h-full rounded ${barClassName ?? "bg-brand"}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
      <div className="w-10 text-gray-400 text-right">{value}</div>
    </div>
  );
}
