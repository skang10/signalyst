import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ChatPanel } from "../ChatPanel";
import { useRunStore } from "@/lib/store";

beforeEach(() => {
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
});
