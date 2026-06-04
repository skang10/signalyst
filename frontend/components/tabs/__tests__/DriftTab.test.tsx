import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DriftTab } from "../DriftTab";
const drift = {
  drift_detected: true,
  psi_score: 0.32,
  drifted_features: ["rsi_14", "macd_signal"],
  ks_results: {
    rsi_14: { statistic: 0.41, p_value: 0.001 },
    macd_signal: { statistic: 0.29, p_value: 0.018 },
    eia_storage: { statistic: 0.08, p_value: 0.42 },
  },
};

describe("DriftTab", () => {
  it("renders PSI score tile", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("0.32")).toBeTruthy();
  });

  it("renders count of drifted features", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("shows DRIFT badge for drifted features", () => {
    render(<DriftTab drift={drift} />);
    const badges = screen.getAllByText("DRIFT");
    expect(badges.length).toBe(2);
  });

  it("shows OK badge for non-drifted features", () => {
    render(<DriftTab drift={drift} />);
    expect(screen.getByText("OK")).toBeTruthy();
  });

  it("renders placeholder when drift is null", () => {
    render(<DriftTab drift={null} />);
    expect(screen.getByText(/drift analysis not available/i)).toBeTruthy();
  });
});
