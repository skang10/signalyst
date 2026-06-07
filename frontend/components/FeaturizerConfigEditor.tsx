"use client";

import { useState } from "react";
import type { FeaturizerConfig } from "@/lib/api";

const FAMILY_LABELS: Record<string, string> = {
  rolling_stats: "Rolling Stats",
  momentum: "Momentum",
  lag: "Lag",
  regime: "Regime",
};

type Props = {
  value: FeaturizerConfig;
  onChange?: (next: FeaturizerConfig) => void;
  readOnly?: boolean;
};

const TAG_ACTIVE =
  "px-2 py-0.5 bg-[#1e3a5f] border border-[#1d4ed8] rounded text-xs text-[#93c5fd] hover:bg-[#234876]";
const TAG_INACTIVE =
  "px-2 py-0.5 bg-transparent border border-[#374151] rounded text-xs text-[#4b5563] line-through hover:border-[#4b5563]";
const TAG_READONLY =
  "px-2 py-0.5 bg-transparent border border-[#374151] rounded text-xs text-[#9ca3af]";
const ADD_INPUT =
  "w-14 bg-transparent border border-dashed border-[#374151] rounded px-2 py-0.5 text-xs text-[#6b7280] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6]";
const ROW_LABEL = "text-[10px] text-[#6b7280] w-16 flex-shrink-0";

function NumberRow({
  label,
  values,
  unit,
  onAdd,
  onRemove,
  readOnly,
}: {
  label: string;
  values: number[];
  unit: string;
  onAdd: (n: number) => void;
  onRemove: (n: number) => void;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const n = Number(draft);
    if (Number.isInteger(n) && n > 0 && !values.includes(n)) onAdd(n);
    setDraft("");
  };

  if (readOnly) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>{label}</span>
        {values.map((v) => (
          <span key={`${label}-${v}`} className={TAG_READONLY}>
            {v}
            {unit}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={ROW_LABEL}>{label}</span>
      {values.map((v) => (
        <button key={`${label}-${v}`} onClick={() => onRemove(v)} className={TAG_ACTIVE}>
          {v}
          {unit} ×
        </button>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        placeholder="+ add"
        className={ADD_INPUT}
      />
    </div>
  );
}

export function FeaturizerConfigEditor({ value, onChange, readOnly = false }: Props) {
  const setWindows = (windows: number[]) => onChange?.({ ...value, windows });
  const setLags = (lags: number[]) => onChange?.({ ...value, lags });

  const toggleFamily = (key: string) => {
    if (readOnly) return;
    onChange?.({
      ...value,
      feature_families: value.feature_families.includes(key)
        ? value.feature_families.filter((f) => f !== key)
        : [...value.feature_families, key],
    });
  };

  return (
    <div className="flex flex-col gap-2.5">
      <NumberRow
        label="WINDOWS"
        values={value.windows}
        unit="d"
        onAdd={(n) => setWindows([...value.windows, n].sort((a, b) => a - b))}
        onRemove={(n) => setWindows(value.windows.filter((w) => w !== n))}
        readOnly={readOnly}
      />
      <NumberRow
        label="LAGS"
        values={value.lags}
        unit="d"
        onAdd={(n) => setLags([...value.lags, n].sort((a, b) => a - b))}
        onRemove={(n) => setLags(value.lags.filter((l) => l !== n))}
        readOnly={readOnly}
      />
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>FAMILIES</span>
        {Object.entries(FAMILY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggleFamily(key)}
            className={[
              value.feature_families.includes(key) ? TAG_ACTIVE : TAG_INACTIVE,
              readOnly ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-xs text-[#9ca3af]">
        <input
          type="checkbox"
          checked={value.energy_specific}
          onChange={(e) => onChange?.({ ...value, energy_specific: e.target.checked })}
          disabled={readOnly}
          className="accent-[#3b82f6]"
        />
        Energy-specific features
      </label>
    </div>
  );
}
