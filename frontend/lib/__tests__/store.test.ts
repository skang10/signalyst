import { describe, it, expect, beforeEach } from "vitest";
import { useRunStore } from "../store";
import type { StreamMessage } from "../websocket";

const mockMsg: StreamMessage = { type: "thought", content: "thinking..." };

const params = {
  date_range_start: "2023-01-01",
  date_range_end: "2023-06-30",
  analysis_mode: "quick" as const,
};

beforeEach(() => {
  sessionStorage.clear();
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

describe("useRunStore - sessionStorage persistence", () => {
  it("setRun writes runId to sessionStorage and clears messages", () => {
    useRunStore.getState().setRun("run-123", params);
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
  });

  it("setRun sets status to running with empty messages", () => {
    useRunStore.getState().setRun("run-123", params);
    const { status, messages } = useRunStore.getState();
    expect(status).toBe("running");
    expect(messages).toHaveLength(0);
  });

  it("setMessages persists messages to sessionStorage", () => {
    useRunStore.getState().setMessages([mockMsg]);
    const raw = sessionStorage.getItem("activeRunMessages");
    expect(JSON.parse(raw!)).toEqual([mockMsg]);
  });

  it("setResult clears sessionStorage and sets status to completed", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().setResult({
      regime: null,
      direction: null,
      drift: null,
      feature_importance: null,
      backtest: null,
      summary: "",
      usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 },
      data_manifest: {},
    });
    expect(sessionStorage.getItem("activeRunId")).toBeNull();
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
    expect(useRunStore.getState().status).toBe("completed");
  });

  it("setError keeps sessionStorage and sets status to failed", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().setError("something went wrong");
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
    expect(useRunStore.getState().status).toBe("failed");
    expect(useRunStore.getState().runId).toBe("run-123");
  });

  it("clearRun removes all sessionStorage entries and resets state", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().clearRun();
    expect(sessionStorage.getItem("activeRunId")).toBeNull();
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
    const { runId, status, result, error, messages, lastRunParams } = useRunStore.getState();
    expect(runId).toBeNull();
    expect(status).toBe("idle");
    expect(result).toBeNull();
    expect(error).toBeNull();
    expect(messages).toHaveLength(0);
    expect(lastRunParams).toBeNull();
  });

  it("sessionStorage retains runId and messages across store state resets", () => {
    useRunStore.getState().setRun("run-456", params);
    useRunStore.getState().setMessages([mockMsg]);
    expect(sessionStorage.getItem("activeRunId")).toBe("run-456");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
  });
});

describe("useRunStore - canceled status", () => {
  it("setRun saves lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    expect(useRunStore.getState().lastRunParams).toEqual(params);
  });

  it("setCanceled sets status to canceled without clearing sessionStorage", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().setCanceled();
    expect(useRunStore.getState().status).toBe("canceled");
    expect(useRunStore.getState().runId).toBe("run-123");
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
  });

  it("setCanceled does not clear lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setCanceled();
    expect(useRunStore.getState().lastRunParams).toEqual(params);
  });

  it("clearRun clears lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().clearRun();
    expect(useRunStore.getState().lastRunParams).toBeNull();
  });
});

describe("useRunStore — chat state", () => {
  it("chatOpen defaults to false", () => {
    expect(useRunStore.getState().chatOpen).toBe(false);
  });

  it("setChatOpen toggles chatOpen", () => {
    useRunStore.getState().setChatOpen(true);
    expect(useRunStore.getState().chatOpen).toBe(true);
    useRunStore.getState().setChatOpen(false);
    expect(useRunStore.getState().chatOpen).toBe(false);
  });

  it("addChatMessage appends to chatMessages", () => {
    const msg = { id: "1", role: "user" as const, content: "hello", timestamp: 0 };
    useRunStore.getState().addChatMessage(msg);
    expect(useRunStore.getState().chatMessages).toHaveLength(1);
    expect(useRunStore.getState().chatMessages[0]).toEqual(msg);
  });

  it("queuePreRunMessage appends to pendingPreRunMessages", () => {
    useRunStore.getState().queuePreRunMessage("Add EIA data");
    expect(useRunStore.getState().pendingPreRunMessages).toEqual(["Add EIA data"]);
  });

  it("clearPreRunMessages empties pendingPreRunMessages", () => {
    useRunStore.getState().queuePreRunMessage("msg1");
    useRunStore.getState().queuePreRunMessage("msg2");
    useRunStore.getState().clearPreRunMessages();
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });

  it("clearRun resets chatMessages and pendingPreRunMessages", () => {
    useRunStore.getState().addChatMessage({ id: "1", role: "user", content: "x", timestamp: 0 });
    useRunStore.getState().queuePreRunMessage("x");
    useRunStore.getState().clearRun();
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });

  it("setRun resets chatMessages and pendingPreRunMessages", () => {
    useRunStore.getState().addChatMessage({ id: "1", role: "user", content: "x", timestamp: 0 });
    useRunStore.getState().queuePreRunMessage("x");
    useRunStore.getState().setRun("run-123", params);
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });
});
