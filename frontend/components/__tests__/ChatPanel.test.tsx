import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPanel } from "../ChatPanel";
import { useRunStore } from "@/lib/store";

const { mockContinueRun } = vi.hoisted(() => ({
  mockContinueRun: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: { continueRun: mockContinueRun },
}));

beforeEach(() => {
  vi.clearAllMocks();
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

describe("ChatPanel — visibility", () => {
  it("renders nothing when chatOpen is false", () => {
    useRunStore.setState({ chatOpen: false });
    const { container } = render(<ChatPanel />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the panel when chatOpen is true", () => {
    useRunStore.setState({ chatOpen: true });
    render(<ChatPanel />);
    expect(screen.getByRole("button", { name: /close chat/i })).toBeTruthy();
  });

  it("close button calls setChatOpen(false)", () => {
    useRunStore.setState({ chatOpen: true });
    render(<ChatPanel />);
    fireEvent.click(screen.getByRole("button", { name: /close chat/i }));
    expect(useRunStore.getState().chatOpen).toBe(false);
  });

  it("shows empty state text when chatMessages is empty", () => {
    useRunStore.setState({ chatOpen: true, chatMessages: [] });
    render(<ChatPanel />);
    expect(screen.getByText(/messages appear here/i)).toBeTruthy();
  });
});

describe("ChatPanel — input states", () => {
  it("input is enabled and shows idle placeholder when status is idle", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    expect(textarea).not.toBeDisabled();
  });

  it("input is disabled when status is running", () => {
    useRunStore.setState({ chatOpen: true, status: "running", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/agent is working/i);
    expect(textarea).toBeDisabled();
  });

  it("input is enabled when status is completed", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    expect(textarea).not.toBeDisabled();
  });

  it("input is disabled when status is failed", () => {
    useRunStore.setState({ chatOpen: true, status: "failed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/run ended/i);
    expect(textarea).toBeDisabled();
  });

  it("input is disabled when status is canceled", () => {
    useRunStore.setState({ chatOpen: true, status: "canceled", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/run ended/i);
    expect(textarea).toBeDisabled();
  });
});

describe("ChatPanel — send behaviour", () => {
  it("send while idle adds to chatMessages and pendingPreRunMessages", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "Add Baker Hughes data" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    const { chatMessages, pendingPreRunMessages } = useRunStore.getState();
    expect(chatMessages).toHaveLength(1);
    expect(chatMessages[0].role).toBe("user");
    expect(chatMessages[0].content).toBe("Add Baker Hughes data");
    expect(pendingPreRunMessages).toEqual(["Add Baker Hughes data"]);
  });

  it("send while completed adds to chatMessages but NOT pendingPreRunMessages", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    fireEvent.change(textarea, { target: { value: "Why is drift elevated?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    const { chatMessages, pendingPreRunMessages } = useRunStore.getState();
    expect(chatMessages).toHaveLength(1);
    expect(pendingPreRunMessages).toHaveLength(0);
  });

  it("send clears the textarea", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("send button is disabled when input is empty", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("pressing Enter sends the message", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "Enter key test" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(useRunStore.getState().chatMessages).toHaveLength(1);
  });

  it("existing chatMessages are displayed", () => {
    useRunStore.setState({
      chatOpen: true,
      status: "idle",
      chatMessages: [
        { id: "1", role: "user", content: "Hello agent", timestamp: 0 },
        { id: "2", role: "agent", content: "Hello user", timestamp: 1 },
      ],
    });
    render(<ChatPanel />);
    expect(screen.getByText("Hello agent")).toBeTruthy();
    expect(screen.getByText("Hello user")).toBeTruthy();
  });

  it("Shift+Enter does not send", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "draft" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
  });
});

describe("ChatPanel — example chips", () => {
  it("shows example chips when status is completed and chatMessages is empty", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    expect(screen.getByText(/why is drift elevated/i)).toBeTruthy();
    expect(screen.getByText(/explain the regime/i)).toBeTruthy();
    expect(screen.getByText(/add baker hughes/i)).toBeTruthy();
    expect(screen.getByText(/top features/i)).toBeTruthy();
  });

  it("does not show chips when status is idle", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    expect(screen.queryByText(/why is drift elevated/i)).toBeNull();
  });

  it("does not show chips when chatMessages is non-empty", () => {
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "r1",
      chatMessages: [{ id: "1", role: "user", content: "hi", timestamp: 0 }],
    });
    render(<ChatPanel />);
    expect(screen.queryByText(/why is drift elevated/i)).toBeNull();
  });

  it("clicking a chip populates the textarea without sending", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    fireEvent.click(screen.getByText(/why is drift elevated/i));
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    expect((textarea as HTMLTextAreaElement).value).toBe("Why is drift elevated?");
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
  });
});

describe("ChatPanel — continueRun on completed send", () => {
  it("calls continueRun and continueToRun when sending while completed", async () => {
    mockContinueRun.mockResolvedValueOnce({ run_id: "run-new" });
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    fireEvent.change(textarea, { target: { value: "Why is drift elevated?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(mockContinueRun).toHaveBeenCalledWith("run-old", "Why is drift elevated?");
      expect(useRunStore.getState().runId).toBe("run-new");
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("adds user message to chatMessages before calling continueRun", async () => {
    mockContinueRun.mockResolvedValueOnce({ run_id: "run-new" });
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    fireEvent.change(screen.getByPlaceholderText(/ask a follow-up/i), {
      target: { value: "Explain drift" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(useRunStore.getState().chatMessages).toHaveLength(1);
      expect(useRunStore.getState().chatMessages[0].content).toBe("Explain drift");
    });
  });

  it("preserves chatMessages on continueRun error", async () => {
    mockContinueRun.mockRejectedValueOnce(new Error("network error"));
    useRunStore.setState({
      chatOpen: true,
      status: "completed",
      runId: "run-old",
      lastRunParams: { date_range_start: "2023-01-01", date_range_end: "2023-06-30", analysis_mode: "quick" },
    });
    render(<ChatPanel />);
    fireEvent.change(screen.getByPlaceholderText(/ask a follow-up/i), {
      target: { value: "Explain drift" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(useRunStore.getState().status).toBe("completed");
      expect(useRunStore.getState().chatMessages).toHaveLength(1);
    });
  });
});
