import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopBar } from "../TopBar";
import { useRunStore } from "@/lib/store";

const { mockAnalyze, mockCancelRun } = vi.hoisted(() => ({
  mockAnalyze: vi.fn(),
  mockCancelRun: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: { analyze: mockAnalyze, cancelRun: mockCancelRun },
}));

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
  });
});

describe("TopBar — button states", () => {
  it("does not render a theme toggle", () => {
    render(<TopBar />);
    expect(screen.queryByRole("button", { name: /toggle theme/i })).toBeNull();
  });

  it("shows Run button when idle with no runId", () => {
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /run/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /resume/i })).toBeNull();
  });

  it("shows only Cancel when running", () => {
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /run/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /resume/i })).toBeNull();
  });

  it("shows Resume and New Run when canceled", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });

  it("shows Resume and New Run when failed", () => {
    useRunStore.setState({ status: "failed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });

  it("shows Resume and New Run when completed", () => {
    useRunStore.setState({ status: "completed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });

  it("shows Resume and New Run when idle with a runId (page refresh recovery)", () => {
    useRunStore.setState({ status: "idle", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });
});

describe("TopBar — status badge", () => {
  it("shows Canceled badge when status is canceled", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/canceled/i)).toBeTruthy();
  });

  it("shows Failed badge when status is failed", () => {
    useRunStore.setState({ status: "failed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/failed/i)).toBeTruthy();
  });

  it("shows Completed badge when status is completed", () => {
    useRunStore.setState({ status: "completed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/completed/i)).toBeTruthy();
  });

  it("shows no badge when status is idle with runId (page refresh)", () => {
    useRunStore.setState({ status: "idle", runId: "run-1" });
    render(<TopBar />);
    expect(screen.queryByText(/canceled|failed|completed/i)).toBeNull();
  });
});

describe("TopBar — handlers", () => {
  it("clicking Cancel calls api.cancelRun and sets status to canceled", async () => {
    mockCancelRun.mockResolvedValueOnce({});
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(mockCancelRun).toHaveBeenCalledWith("run-1");
      expect(useRunStore.getState().status).toBe("canceled");
      expect(useRunStore.getState().runId).toBe("run-1");
    });
  });

  it("clicking Resume sets status to running", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /resume/i }));
    expect(useRunStore.getState().status).toBe("running");
  });

  it("clicking New Run calls api.analyze and sets status to running", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-2" });
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /new run/i }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledOnce();
      expect(useRunStore.getState().runId).toBe("run-2");
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("clicking Run (idle) calls api.analyze and sets status to running", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-3" });
    render(<TopBar />);
    // In idle state the only button with "Run" text is "▶ Run" (not "▶ New Run")
    fireEvent.click(screen.getByRole("button", { name: "▶ Run" }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledOnce();
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("Cancel still sets status to canceled when api.cancelRun throws", async () => {
    mockCancelRun.mockRejectedValueOnce(new Error("network error"));
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(useRunStore.getState().status).toBe("canceled");
    });
  });
});
