"use client";

import { useState } from "react";
import type { ConnectorOut, PendingSource } from "@/lib/api";

type Props = {
  available: ConnectorOut[];
  value: PendingSource[];
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
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
          ? "bg-teal-50 border-teal-200 text-teal-700"
          : "bg-gray-50 border-gray-200 text-gray-400",
        onClick ? "cursor-pointer" : "cursor-default",
      ].join(" ")}
    >
      <span
        className={[
          "w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0",
          active ? "bg-teal-600 border-teal-600 text-white" : "border-gray-300",
        ].join(" ")}
      >
        {active && <Checkmark />}
      </span>
      {label}
    </button>
  );
}

export function ConnectorEditor({ available, value, onChange, readOnly }: Props) {
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [addValue, setAddValue] = useState("");
  const activeIds = new Set(value.map((s) => s.connector_id));

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
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="text-[10px] text-gray-400 px-3 py-2 border-b border-gray-100 bg-gray-50 font-mono uppercase tracking-widest">
        Click a chip to toggle · active sources used on next data run
      </div>
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        const isYfinance = connector.id === "yfinance";
        const tickers = (source?.params?.tickers as string[] | undefined) ?? [];

        return (
          <div key={connector.id} className="px-3 py-2.5 border-b border-gray-100 last:border-0">
            <div className="flex items-baseline gap-2">
              <span
                className={`text-sm font-medium ${isActive ? "text-teal-700" : "text-gray-500"}`}
              >
                {connector.name}
              </span>
              <span className="text-xs text-gray-400 truncate">{connector.description}</span>
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
                        className="text-xs font-mono border border-teal-200 rounded px-2 py-1 outline-none focus:border-teal-400 w-24"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setAddingFor(connector.id);
                          setAddValue("");
                        }}
                        className="px-2 py-1 rounded-md border border-dashed border-gray-300 text-xs text-gray-400 hover:border-teal-300 hover:text-teal-600"
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
    </div>
  );
}
