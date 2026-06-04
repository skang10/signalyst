import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FeaturesTab } from "../FeaturesTab";
type FeatureImportanceResult = Record<string, unknown>;

const features: FeatureImportanceResult = {
  top_features: [
    { name: "rsi_14", importance: 0.42 },
    { name: "macd_signal", importance: 0.27 },
    { name: "eia_storage", importance: 0.15 },
  ],
  n_features_evaluated: 20,
  n_samples_explained: 100,
};

describe("FeaturesTab", () => {
  it("renders feature names and importance values", () => {
    render(<FeaturesTab features={features} />);
    expect(screen.getByText("rsi_14")).toBeTruthy();
    expect(screen.getByText("0.420")).toBeTruthy();
    expect(screen.getByText("macd_signal")).toBeTruthy();
    expect(screen.getByText("eia_storage")).toBeTruthy();
  });

  it("renders footer with feature count and sample count", () => {
    render(<FeaturesTab features={features} />);
    expect(screen.getByText(/20 features/)).toBeTruthy();
    expect(screen.getByText(/100 samples/)).toBeTruthy();
  });

  it("renders placeholder when features is null", () => {
    render(<FeaturesTab features={null} />);
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });
});
