import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OverviewTab } from "../OverviewTab";
import type { MarketProfile } from "@/lib/api";
const result = {
  regime: {
    regime: "range_bound",
    confidence: 0.9503,
    entropy: 0.187,
    distribution: { range_bound: 24, bull_supercycle: 4, bust: 2 },
  },
  direction: {
    direction: "down",
    confidence: 0.7046,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20, up: 10 },
  },
  drift: {
    drift_detected: true,
    psi_score: 0.32,
    drifted_features: ["rsi_14"],
    ks_results: { rsi_14: { statistic: 0.41, p_value: 0.001 } },
  },
  feature_importance: {
    top_features: [{ name: "rsi_14", importance: 0.42 }],
    n_features_evaluated: 20,
    n_samples_explained: 100,
  },
  backtest: null,
  summary: "Range-bound regime.",
  usage: { input_tokens: 1000, output_tokens: 100, estimated_cost_usd: 0.01 },
  data_manifest: {},
};

const sp500Profile: MarketProfile = {
  id: "sp500",
  name: "S&P 500",
  description: "US large-cap equity regime analysis using price, volatility, and macro signals.",
  default_connectors: [],
  default_featurizer_config: {
    windows: [],
    lags: [],
    feature_families: [],
    energy_specific: false,
  },
  regime_labels: ["bull_market", "range_bound", "bear_market", "high_volatility"],
};

describe("OverviewTab", () => {
  it("renders regime stat tile with confidence", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getAllByText(/range.bound/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/95\.0%/)).toBeTruthy();
  });

  it("renders direction stat tile", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getAllByText(/down/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/70\.5%/)).toBeTruthy();
  });

  it("renders drift stat tile with PSI score", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText("0.32")).toBeTruthy();
  });

  it("renders top signal stat tile", () => {
    render(<OverviewTab result={result} />);
    expect(screen.getByText("rsi_14")).toBeTruthy();
    expect(screen.getByText(/0\.42/)).toBeTruthy();
  });

  it("renders placeholder when regime is null", () => {
    render(<OverviewTab result={{ ...result, regime: null, direction: null }} />);
    expect(screen.getByText(/analysis incomplete/i)).toBeTruthy();
  });

  it("formats non-oil regime labels generically", () => {
    const sp500Result = {
      ...result,
      regime: { ...result.regime, regime: "bull_market", distribution: { bull_market: 10 } },
    };
    render(<OverviewTab result={sp500Result} />);
    expect(screen.getAllByText(/bull market/i).length).toBeGreaterThan(0);
  });

  it("colors non-oil bearish/bullish regimes based on profile.regime_labels position", () => {
    const sp500Result = {
      ...result,
      direction: { ...result.direction, distribution: {} },
      regime: {
        ...result.regime,
        regime: "bear_market",
        distribution: { bear_market: 10, bull_market: 5 },
      },
    };
    const { container } = render(<OverviewTab result={sp500Result} profile={sp500Profile} />);
    expect(container.querySelector(".bg-red-600")).toBeTruthy();
    expect(container.querySelector(".bg-emerald-600")).toBeTruthy();
  });

  it("renders market profile name and description when provided", () => {
    render(<OverviewTab result={result} profile={sp500Profile} />);
    expect(screen.getByText("S&P 500")).toBeTruthy();
    expect(screen.getByText(/large-cap equity regime analysis/i)).toBeTruthy();
  });

  it("renders without a profile header when profile is not provided", () => {
    render(<OverviewTab result={result} />);
    expect(screen.queryByText("S&P 500")).toBeNull();
  });
});
