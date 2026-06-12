import { describe, it, expect } from "vitest";
import { isSessionStale } from "../stale";

const baseSession = {
  timeframeStart: "2020-01-01",
  timeframeEnd: "2024-01-01",
  pendingSources: [
    { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
    { connector_id: "fred" },
  ],
};

const baseArtifact = {
  data_manifest: {
    date_range: { start: "2020-01-01", end: "2024-01-01" },
    requested_start: "2020-01-01",
    requested_end: "2024-01-01",
  },
  sources: [
    { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
    { connector_id: "fred", params: {} },
  ],
};

describe("isSessionStale", () => {
  it("returns false when no artifact exists yet", () => {
    expect(isSessionStale(baseSession, null)).toBe(false);
  });

  it("returns false when timeframe and sources match", () => {
    expect(isSessionStale(baseSession, baseArtifact)).toBe(false);
  });

  it("returns true when timeframe differs", () => {
    expect(
      isSessionStale({ ...baseSession, timeframeEnd: "2024-06-01" }, baseArtifact),
    ).toBe(true);
  });

  it("returns true when a connector is added", () => {
    const session = {
      ...baseSession,
      pendingSources: [...baseSession.pendingSources, { connector_id: "gpr" }],
    };
    expect(isSessionStale(session, baseArtifact)).toBe(true);
  });

  it("returns true when a yfinance ticker is removed", () => {
    const session = {
      ...baseSession,
      pendingSources: [
        { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F"] } },
        { connector_id: "fred" },
      ],
    };
    expect(isSessionStale(session, baseArtifact)).toBe(true);
  });

  it("returns false when yfinance tickers are the same but in a different order", () => {
    const session = {
      ...baseSession,
      pendingSources: [
        { connector_id: "yfinance", params: { tickers: ["DX-Y.NYB", "CL=F", "BZ=F"] } },
        { connector_id: "fred" },
      ],
    };
    expect(isSessionStale(session, baseArtifact)).toBe(false);
  });
});
