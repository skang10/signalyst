import { render, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AgentStream } from "../AgentStream";
import { useRunStore } from "@/lib/store";
import type { StreamMessage } from "@/lib/websocket";

const { mockGetRun, mockUseRunStream } = vi.hoisted(() => ({
  mockGetRun: vi.fn(),
  mockUseRunStream: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: { getRun: mockGetRun },
}));
vi.mock("@/lib/websocket", () => ({
  useRunStream: mockUseRunStream,
}));

const doneMessage: StreamMessage = {
  type: "done",
  summary: "The drift is elevated because of macro shifts.",
};

const completedResult = {
  status: "completed",
  result: {
    summary: "done",
    regime: null,
    direction: null,
    drift: null,
    feature_importance: null,
    backtest: null,
    usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 },
    data_manifest: null,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseRunStream.mockReturnValue({ messages: [], connected: false });
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});

describe("AgentStream — agent bubble on done", () => {
  it("adds agent bubble to chatMessages when done arrives and chatMessages is non-empty", async () => {
    mockGetRun.mockResolvedValueOnce(completedResult);
    useRunStore.setState({
      runId: "run-1",
      status: "running",
      chatMessages: [{ id: "1", role: "user", content: "Why is drift elevated?", timestamp: 0 }],
    });
    mockUseRunStream.mockReturnValue({ messages: [doneMessage], connected: true });

    await act(async () => {
      render(<AgentStream />);
    });

    await act(async () => {
      await vi.waitFor(() => {
        const { chatMessages } = useRunStore.getState();
        expect(chatMessages).toHaveLength(2);
        expect(chatMessages[1].role).toBe("agent");
        expect(chatMessages[1].content).toBe("The drift is elevated because of macro shifts.");
      });
    });
  });

  it("does NOT add agent bubble when done arrives and chatMessages is empty", async () => {
    mockGetRun.mockResolvedValueOnce(completedResult);
    useRunStore.setState({ runId: "run-1", status: "running", chatMessages: [] });
    mockUseRunStream.mockReturnValue({ messages: [doneMessage], connected: true });

    await act(async () => {
      render(<AgentStream />);
    });

    await act(async () => {
      await vi.waitFor(() => {
        expect(useRunStore.getState().status).toBe("completed");
      });
    });

    expect(useRunStore.getState().chatMessages).toHaveLength(0);
  });
});
