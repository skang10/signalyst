import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FeaturizerConfigEditor } from "../FeaturizerConfigEditor";
import type { FeaturizerConfig } from "@/lib/api";

const baseConfig: FeaturizerConfig = {
  windows: [5, 20, 60],
  lags: [1, 5],
  feature_families: ["rolling_stats", "momentum"],
  energy_specific: true,
};

describe("FeaturizerConfigEditor", () => {
  it("renders tags for windows, lags, and families", () => {
    render(<FeaturizerConfigEditor value={baseConfig} onChange={() => {}} />);
    expect(screen.getAllByText("5d ×")).toHaveLength(2); // appears in both windows and lags
    expect(screen.getByText("20d ×")).toBeTruthy();
    expect(screen.getByText("60d ×")).toBeTruthy();
    expect(screen.getByText("1d ×")).toBeTruthy();
    expect(screen.getByText("Rolling Stats")).toBeTruthy();
  });

  it("calls onChange with the window removed when its tag is clicked", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByText("20d ×"));
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, windows: [5, 60] });
  });

  it("adds a new window on Enter, keeping the list sorted and de-duplicated", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    // Click the first "+ add" button (Windows row) to enter editing mode
    const [windowsAddBtn] = screen.getAllByText("+ add");
    fireEvent.click(windowsAddBtn);
    const input = screen.getByPlaceholderText("e.g. 90");
    fireEvent.change(input, { target: { value: "10" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, windows: [5, 10, 20, 60] });
  });

  it("toggles a feature family on click", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByText("Lag"));
    expect(onChange).toHaveBeenCalledWith({
      ...baseConfig,
      feature_families: ["rolling_stats", "momentum", "lag"],
    });
  });

  it("toggles energy_specific via the checkbox", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, energy_specific: false });
  });
});

describe("FeaturizerConfigEditor readOnly mode", () => {
  it("renders pills without remove buttons or an add input", () => {
    render(<FeaturizerConfigEditor value={baseConfig} readOnly />);
    expect(screen.queryByText("20d ×")).toBeNull();
    expect(screen.getByText("20d")).toBeTruthy();
    expect(screen.queryAllByPlaceholderText("+ add")).toHaveLength(0);
  });

  it("does not call onChange when a family pill is clicked", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} readOnly />);
    fireEvent.click(screen.getByText("Lag"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("disables the energy-specific checkbox", () => {
    render(<FeaturizerConfigEditor value={baseConfig} readOnly />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});
