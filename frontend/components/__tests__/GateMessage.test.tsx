import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { UserReviewGate } from "../GateMessage";
import type { FeaturizerConfig } from "@/lib/api";

const serverConfig: FeaturizerConfig = {
  windows: [5, 20, 60],
  lags: [1, 5],
  feature_families: ["rolling_stats", "momentum"],
  energy_specific: true,
};

describe("UserReviewGate", () => {
  it("calls onProceed with no patch when the draft matches the server config", () => {
    const onProceed = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={onProceed}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("→ Run Analysis"));
    expect(onProceed).toHaveBeenCalledWith(undefined);
  });

  it("shows the dirty banner and notifies the parent after an edit", () => {
    const onDirtyChange = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={onDirtyChange}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    expect(screen.getByText(/Config changed/)).toBeTruthy();
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
  });

  it("sends the edited draft as the patch when running analysis while dirty", () => {
    const onProceed = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={onProceed}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    fireEvent.click(screen.getByText("→ Run Analysis"));
    expect(onProceed).toHaveBeenCalledWith({ ...serverConfig, windows: [5, 60] });
  });

  it("resyncs the draft when the server config changes from outside (e.g. a chat update)", () => {
    const { rerender } = render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );
    expect(screen.getByText("20d ×")).toBeTruthy();

    const updatedConfig: FeaturizerConfig = { ...serverConfig, windows: [7, 30, 90] };
    rerender(
      <UserReviewGate
        serverConfig={updatedConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );

    expect(screen.queryByText(/Config changed/)).toBeNull();
    expect(screen.getByText("30d ×")).toBeTruthy();
    expect(screen.getByText("90d ×")).toBeTruthy();
    expect(screen.queryByText("20d ×")).toBeNull();
  });

  it("discard resets the draft to the server config and clears dirty state", () => {
    const onDirtyChange = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={onDirtyChange}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    fireEvent.click(screen.getByText("Discard"));
    expect(screen.queryByText(/Config changed/)).toBeNull();
    expect(onDirtyChange).toHaveBeenLastCalledWith(false);
  });
});
