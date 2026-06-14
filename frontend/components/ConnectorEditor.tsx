"use client";

import { useState } from "react";
import type { ConnectorOut, PendingSource } from "@/lib/api";

type Props = {
  available: ConnectorOut[];
  value: PendingSource[];
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
  footer?: React.ReactNode;
};

// Static display label for connectors that contribute a single source.
// Connectors not listed here fall back to their own `name`.
const SOURCE_LABELS: Record<string, string> = {
  fred: "INDPRO",
  eia: "Inventory",
  gpr: "GPR",
};

function Checkmark() {
  return (
    <svg
      className="w-3 h-3"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={[
        "flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-mono font-semibold transition-colors",
        active
          ? "bg-brand-soft border-brand-soft-border text-brand"
          : "bg-gray-50 border-gray-200 text-gray-400",
        onClick ? "cursor-pointer" : "cursor-default",
      ].join(" ")}
    >
      <span
        className={[
          "w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0",
          active ? "bg-brand border-brand text-white" : "border-gray-300",
        ].join(" ")}
      >
        {active && <Checkmark />}
      </span>
      {label}
    </button>
  );
}

export function ConnectorEditor({ available, value, onChange, readOnly, footer }: Props) {
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [addValue, setAddValue] = useState("");
  const activeIds = new Set(value.map((s) => s.connector_id));
  const uploadSources = value.filter((s) => s.connector_id === "upload");

  function removeUpload(sourceName: string | undefined) {
    if (readOnly) return;
    onChange(value.filter((s) => !(s.connector_id === "upload" && s.source_name === sourceName)));
  }

  function toggleConnector(connector: ConnectorOut) {
    if (readOnly) return;
    if (activeIds.has(connector.id)) {
      onChange(value.filter((s) => s.connector_id !== connector.id));
    } else {
      onChange([...value, { connector_id: connector.id }]);
    }
  }

  function removeTicker(connectorId: string, ticker: string) {
    if (readOnly) return;
    const source = value.find((s) => s.connector_id === connectorId);
    const tickers = (source?.params?.tickers as string[] | undefined) ?? [];
    const next = tickers.filter((t) => t !== ticker);
    if (next.length === 0) {
      onChange(value.filter((s) => s.connector_id !== connectorId));
    } else {
      onChange(
        value.map((s) =>
          s.connector_id === connectorId ? { ...s, params: { ...s.params, tickers: next } } : s,
        ),
      );
    }
  }

  function addTicker(connectorId: string, ticker: string) {
    if (readOnly) return;
    const trimmed = ticker.trim();
    if (!trimmed) return;
    const source = value.find((s) => s.connector_id === connectorId);
    if (!source) {
      onChange([...value, { connector_id: connectorId, params: { tickers: [trimmed] } }]);
      return;
    }
    const tickers = (source.params?.tickers as string[] | undefined) ?? [];
    onChange(
      value.map((s) =>
        s.connector_id === connectorId
          ? { ...s, params: { ...s.params, tickers: [...tickers, trimmed] } }
          : s,
      ),
    );
  }

  function confirmAdd(connectorId: string) {
    addTicker(connectorId, addValue);
    setAddingFor(null);
    setAddValue("");
  }

  if (available.length === 0) {
    return (
      <div className="border border-gray-200 rounded-lg px-3 py-4 text-xs text-gray-400 text-center">
        No connectors configured.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        const isYfinance = connector.id === "yfinance";
        const tickers = (source?.params?.tickers as string[] | undefined) ?? [];

        return (
          <div key={connector.id} className="border border-gray-200 rounded-lg px-3 py-2.5 bg-white">
            <div className="flex flex-col gap-0.5">
              <span
                className={`text-sm font-medium whitespace-nowrap ${isActive ? "text-brand" : "text-gray-500"}`}
              >
                {connector.name}
              </span>
              <span className="text-xs text-gray-400">{connector.description}</span>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {isYfinance ? (
                <>
                  {tickers.map((ticker) => (
                    <Chip
                      key={ticker}
                      label={ticker}
                      active
                      onClick={readOnly ? undefined : () => removeTicker(connector.id, ticker)}
                    />
                  ))}
                  {!readOnly &&
                    (addingFor === connector.id ? (
                      <input
                        autoFocus
                        value={addValue}
                        onChange={(e) => setAddValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") confirmAdd(connector.id);
                          if (e.key === "Escape") {
                            setAddValue("");
                            setAddingFor(null);
                          }
                        }}
                        onBlur={() => confirmAdd(connector.id)}
                        placeholder="e.g. XLE"
                        className="text-xs font-mono border border-brand-soft-border rounded px-2 py-1 outline-none focus:border-brand w-24"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setAddingFor(connector.id);
                          setAddValue("");
                        }}
                        className="px-2 py-1 rounded-md border border-dashed border-gray-300 text-xs text-gray-400 hover:border-brand-soft-border hover:text-brand"
                      >
                        + Add
                      </button>
                    ))}
                </>
              ) : (
                <Chip
                  label={SOURCE_LABELS[connector.id] ?? connector.name}
                  active={isActive}
                  onClick={readOnly ? undefined : () => toggleConnector(connector)}
                />
              )}
            </div>
          </div>
        );
      })}
      {uploadSources.length > 0 && (
        <div className="border border-gray-200 rounded-lg px-3 py-2.5 bg-white">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-brand whitespace-nowrap">Custom Upload</span>
            <span className="text-xs text-gray-400">
              Your uploaded data — click to exclude from the next run
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {uploadSources.map((s) => (
              <Chip
                key={s.source_name}
                label={s.source_name ?? "Uploaded data"}
                active
                onClick={readOnly ? undefined : () => removeUpload(s.source_name)}
              />
            ))}
          </div>
        </div>
      )}
      {footer}
    </div>
  );
}
