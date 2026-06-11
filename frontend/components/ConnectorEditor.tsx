"use client";

import type { ConnectorOut, PendingSource } from "@/lib/api";

type Props = {
  available: ConnectorOut[];
  value: PendingSource[];
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
};

export function ConnectorEditor({ available, value, onChange, readOnly }: Props) {
  const activeIds = new Set(value.map((s) => s.connector_id));

  function toggle(connector: ConnectorOut) {
    if (readOnly) return;
    if (activeIds.has(connector.id)) {
      onChange(value.filter((s) => s.connector_id !== connector.id));
    } else {
      onChange([...value, { connector_id: connector.id }]);
    }
  }

  function setTickers(connectorId: string, raw: string) {
    const tickers = raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    onChange(
      value.map((s) =>
        s.connector_id === connectorId ? { ...s, params: { ...s.params, tickers } } : s,
      ),
    );
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
        Click to toggle · active connectors used on next data run
      </div>
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        // Ticker input shown only for yfinance — it's the only connector with user-configurable tickers
        const showTickers = isActive && connector.id === "yfinance";
        const tickers = (source?.params?.tickers as string[] | undefined)?.join(", ") ?? "";

        return (
          <div
            key={connector.id}
            onClick={() => toggle(connector)}
            className={[
              "px-3 py-2.5 border-b border-gray-100 last:border-0 transition-colors",
              readOnly ? "cursor-default" : "cursor-pointer",
              isActive ? "bg-teal-50" : "bg-white",
            ].join(" ")}
          >
            <div className={`flex items-center gap-2 ${isActive ? "" : "opacity-50"}`}>
              <div
                className={[
                  "w-4 h-4 rounded border flex items-center justify-center flex-shrink-0",
                  isActive ? "bg-teal-600 border-teal-600 text-white" : "border-gray-300",
                ].join(" ")}
              >
                {isActive && (
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
                )}
              </div>
              <span
                className={`text-sm font-medium ${isActive ? "text-teal-700" : "text-gray-500"}`}
              >
                {connector.name}
              </span>
              <span className="text-xs text-gray-400 truncate">{connector.description}</span>
            </div>
            {showTickers && (
              <div
                className="mt-1.5 flex items-center gap-2 ml-4"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="text-[10px] text-gray-400 font-mono">Tickers:</span>
                <input
                  value={tickers}
                  onChange={(e) => setTickers(connector.id, e.target.value)}
                  disabled={readOnly}
                  className="flex-1 text-xs font-mono border border-teal-200 rounded px-2 py-0.5 bg-white outline-none focus:border-teal-400 disabled:opacity-40"
                  placeholder="CL=F, BZ=F, DX-Y.NYB"
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
