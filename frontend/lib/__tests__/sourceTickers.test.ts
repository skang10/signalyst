import { describe, it, expect } from "vitest";
import { visibleTickers } from "../sourceTickers";

const manifestTickers = ["CL=F", "BZ=F", "DX-Y.NYB", "INDPRO", "eia_inventory_change", "GPR"];

const fullArtifactSources = [
  { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
  { connector_id: "fred", params: { series_ids: ["INDPRO"] } },
  { connector_id: "eia", params: {} },
  { connector_id: "gpr", params: {} },
];

describe("visibleTickers", () => {
  it("shows all tickers when pending sources match the artifact", () => {
    expect(visibleTickers(manifestTickers, fullArtifactSources, fullArtifactSources)).toEqual(
      manifestTickers,
    );
  });

  it("hides a yfinance ticker removed from pending sources", () => {
    const pendingSources = [
      { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F"] } },
      { connector_id: "fred", params: { series_ids: ["INDPRO"] } },
      { connector_id: "eia", params: {} },
      { connector_id: "gpr", params: {} },
    ];
    expect(visibleTickers(manifestTickers, pendingSources, fullArtifactSources)).toEqual([
      "CL=F",
      "BZ=F",
      "INDPRO",
      "eia_inventory_change",
      "GPR",
    ]);
  });

  it("hides eia/gpr signals when their connectors are toggled off", () => {
    const pendingSources = [
      { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F", "DX-Y.NYB"] } },
      { connector_id: "fred", params: { series_ids: ["INDPRO"] } },
    ];
    expect(visibleTickers(manifestTickers, pendingSources, fullArtifactSources)).toEqual([
      "CL=F",
      "BZ=F",
      "DX-Y.NYB",
      "INDPRO",
    ]);
  });

  it("keeps uploaded custom columns that aren't produced by any known connector", () => {
    const tickers = [...manifestTickers, "MY_CUSTOM_SIGNAL"];
    const artifactSources = [...fullArtifactSources, { connector_id: "upload", params: {} }];
    const pendingSources = [
      { connector_id: "yfinance", params: { tickers: ["CL=F", "BZ=F"] } },
      { connector_id: "fred", params: { series_ids: ["INDPRO"] } },
      { connector_id: "eia", params: {} },
      { connector_id: "gpr", params: {} },
    ];
    expect(visibleTickers(tickers, pendingSources, artifactSources)).toEqual([
      "CL=F",
      "BZ=F",
      "INDPRO",
      "eia_inventory_change",
      "GPR",
      "MY_CUSTOM_SIGNAL",
    ]);
  });
});
