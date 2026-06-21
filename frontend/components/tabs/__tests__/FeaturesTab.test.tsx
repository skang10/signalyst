import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FeaturesTab } from "../FeaturesTab";

const features = {
  top_features: [
    { name: "rsi_14", importance: 0.42 },
    { name: "macd_signal", importance: 0.27 },
    { name: "eia_storage", importance: 0.15 },
  ],
  n_features_evaluated: 20,
  n_samples_explained: 100,
};

const featuresWithModelInfo = {
  ...features,
  model_info: { name: "TabPFN", task: "regime_classification", n_estimators: 4 },
};

const featureArtifact = {
  kind: "features" as const,
  artifact_id: "fa-1",
  n_features: 108,
  n_rows: 22,
  family_counts: { rolling_stats: 48, lag: 30, momentum: 30 },
  columns: ["CL=F_mean_5d"],
  featurizer_config: {
    windows: [5, 20, 60],
    lags: [1, 5, 20],
    feature_families: ["rolling_stats", "lag", "momentum"],
    energy_specific: true,
  },
  cache_hit: false,
  created_at: "2026-06-22T00:00:00",
};

describe("FeaturesTab", () => {
  it("renders feature names and importance values", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.getByText("rsi_14")).toBeTruthy();
    expect(screen.getByText("42%")).toBeTruthy();
    expect(screen.getByText("macd_signal")).toBeTruthy();
    expect(screen.getByText("eia_storage")).toBeTruthy();
  });

  it("renders footer with feature count and sample count", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.getByText(/20 features/)).toBeTruthy();
    expect(screen.getByText(/100 samples/)).toBeTruthy();
  });

  it("renders placeholder when features is null", () => {
    render(<FeaturesTab features={null} featureArtifact={null} />);
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });

  it("renders the model card when model_info is present", () => {
    render(<FeaturesTab features={featuresWithModelInfo} featureArtifact={null} />);
    expect(screen.getByText(/TabPFN/)).toBeTruthy();
    expect(screen.getByText(/Regime Classification/)).toBeTruthy();
    expect(screen.getByText(/4 ensemble members/)).toBeTruthy();
  });

  it("omits the model card when model_info is absent", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.queryByText(/ensemble members/)).toBeNull();
  });

  it("renders the feature generation card when featureArtifact is present", () => {
    render(<FeaturesTab features={features} featureArtifact={featureArtifact} />);
    expect(screen.getByText("108")).toBeTruthy();
    expect(screen.getByText("features")).toBeTruthy();
    expect(screen.getByText("22")).toBeTruthy();
    expect(screen.getByText("rows")).toBeTruthy();
    expect(screen.getByText("rolling_stats")).toBeTruthy();
  });

  it("omits the feature generation card when featureArtifact is null", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.queryByText(/rolling_stats/)).toBeNull();
  });
});
