import type { PendingSource } from "./api";

const KNOWN_CONNECTOR_IDS = new Set(["yfinance", "fred", "eia", "gpr"]);

// Manifest ticker keys a set of (active) connector sources would produce.
function tickersFor(sources: PendingSource[]): Set<string> {
  const result = new Set<string>();
  for (const source of sources) {
    const params = source.params ?? {};
    switch (source.connector_id) {
      case "yfinance":
        for (const t of (params.tickers as string[] | undefined) ?? []) result.add(t);
        break;
      case "fred":
        for (const t of (params.series_ids as string[] | undefined) ?? ["INDPRO"]) result.add(t);
        break;
      case "eia":
        result.add("eia_inventory_change");
        break;
      case "gpr":
        result.add("GPR");
        break;
      default:
        break;
    }
  }
  return result;
}

// Manifest tickers to display: anything still requested in `pendingSources`,
// plus anything not produced by a known connector (e.g. uploaded custom columns),
// even if a known connector that previously produced it has since been removed/edited.
export function visibleTickers(
  manifestTickers: string[],
  pendingSources: PendingSource[],
  artifactSources: PendingSource[],
): string[] {
  const expected = tickersFor(pendingSources);
  const known = tickersFor(artifactSources.filter((s) => KNOWN_CONNECTOR_IDS.has(s.connector_id)));
  return manifestTickers.filter((t) => expected.has(t) || !known.has(t));
}
