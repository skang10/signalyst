"use client";

import { useRef, useState } from "react";
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
  "px-2 py-0.5 bg-teal-50 border border-teal-300 rounded text-xs text-teal-700 hover:bg-teal-100";
const TAG_INACTIVE =
  "px-2 py-0.5 bg-transparent border border-gray-300 rounded text-xs text-gray-400 line-through hover:border-gray-400";
const TAG_READONLY =
  "px-2 py-0.5 bg-teal-50 border border-teal-300 rounded text-xs text-teal-700 opacity-60";
const ROW_LABEL = "text-[10px] text-gray-500 w-16 flex-shrink-0";

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
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const commit = () => {
    const n = parseInt(draft, 10);
    if (Number.isInteger(n) && n > 0 && !values.includes(n)) onAdd(n);
    setDraft("");
    setEditing(false);
  };

  const startEditing = () => {
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
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
      {editing ? (
        <input
          ref={inputRef}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            if (e.key === "Escape") { setDraft(""); setEditing(false); }
          }}
          placeholder={`e.g. 90`}
          className="w-20 bg-transparent border border-teal-400 rounded px-2 py-0.5 text-xs font-mono outline-none"
        />
      ) : (
        <button
          onClick={startEditing}
          className="px-2 py-0.5 border border-dashed border-gray-300 rounded text-xs text-gray-400 hover:border-teal-400 hover:text-teal-600 transition-colors"
        >
          + add
        </button>
      )}
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
      <label className="flex items-center gap-2 text-xs text-gray-500">
        <input
          type="checkbox"
          checked={value.energy_specific}
          onChange={(e) => onChange?.({ ...value, energy_specific: e.target.checked })}
          disabled={readOnly}
          className="accent-teal-600"
        />
        Energy-specific features
      </label>
    </div>
  );
}
