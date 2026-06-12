import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ConnectorEditor } from "../ConnectorEditor";
import type { ConnectorOut, PendingSource } from "@/lib/api";

const connectors: ConnectorOut[] = [
  {
    id: "yfinance",
    name: "Yahoo Finance",
    description: "Daily price series from Yahoo Finance. Supports equities, ETFs, and futures.",
    type: "yfinance",
    available: true,
  },
  {
    id: "fred",
    name: "FRED",
    description: "Macro time series from the St. Louis Fed FRED database.",
    type: "fred",
    available: true,
  },
  {
    id: "eia",
    name: "EIA",
    description: "Weekly US crude oil inventory change from the EIA.",
    type: "eia",
    available: true,
  },
  {
    id: "gpr",
    name: "GPR Index",
    description: "Daily Geopolitical Risk Index from the Federal Reserve.",
    type: "gpr",
    available: true,
  },
];

const baseValue: PendingSource[] = [
  { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
  { connector_id: "fred" },
  { connector_id: "eia" },
];

describe("ConnectorEditor", () => {
  it("renders one chip per yfinance ticker and a single labeled chip for other connectors", () => {
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={() => {}} />);

    expect(screen.getByText("CL=F")).toBeTruthy();
    expect(screen.getByText("BZ=F")).toBeTruthy();
    expect(screen.getByText("DX-Y.NYB")).toBeTruthy();
    expect(screen.getByText("INDPRO")).toBeTruthy(); // fred, active
    expect(screen.getByText("Inventory")).toBeTruthy(); // eia, active
    expect(screen.getByText("GPR")).toBeTruthy(); // gpr, inactive (not in baseValue)
  });

  it("removes a ticker from params.tickers when its chip is clicked", () => {
    const onChange = vi.fn();
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={onChange} />);

    fireEvent.click(screen.getByText("BZ=F"));

    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "yfinance", params: { tickers: ["CL=F", "DX-Y.NYB"] } },
      { connector_id: "fred" },
      { connector_id: "eia" },
    ]);
  });

  it("removes the yfinance entry entirely when its last ticker is removed", () => {
    const onChange = vi.fn();
    const value: PendingSource[] = [
      { connector_id: "yfinance", params: { tickers: ["CL=F"] } },
      { connector_id: "fred" },
    ];
    render(<ConnectorEditor available={connectors} value={value} onChange={onChange} />);

    fireEvent.click(screen.getByText("CL=F"));

    expect(onChange).toHaveBeenCalledWith([{ connector_id: "fred" }]);
  });

  it("adds a ticker via the + Add input, creating the yfinance entry if missing", () => {
    const onChange = vi.fn();
    const value: PendingSource[] = [{ connector_id: "fred" }];
    render(<ConnectorEditor available={connectors} value={value} onChange={onChange} />);

    fireEvent.click(screen.getByText("+ Add"));
    const input = screen.getByPlaceholderText("e.g. XLE");
    fireEvent.change(input, { target: { value: "XLE" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "fred" },
      { connector_id: "yfinance", params: { tickers: ["XLE"] } },
    ]);
  });

  it("toggles a single-source connector in and out of pending_sources via its chip", () => {
    const onChange = vi.fn();
    render(<ConnectorEditor available={connectors} value={baseValue} onChange={onChange} />);

    fireEvent.click(screen.getByText("GPR")); // inactive -> active
    expect(onChange).toHaveBeenCalledWith([...baseValue, { connector_id: "gpr" }]);

    fireEvent.click(screen.getByText("INDPRO")); // fred active -> inactive
    expect(onChange).toHaveBeenCalledWith([
      { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
      { connector_id: "eia" },
    ]);
  });

  it("renders chips read-only with no + Add button and ignores clicks", () => {
    const onChange = vi.fn();
    render(
      <ConnectorEditor available={connectors} value={baseValue} onChange={onChange} readOnly />,
    );

    expect(screen.queryByText("+ Add")).toBeNull();

    fireEvent.click(screen.getByText("BZ=F"));
    fireEvent.click(screen.getByText("INDPRO"));

    expect(onChange).not.toHaveBeenCalled();
  });
});
