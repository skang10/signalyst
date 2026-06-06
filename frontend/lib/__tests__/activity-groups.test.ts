import { describe, expect, it } from "vitest";
import { buildGroups } from "../activity-groups";
import type { ActivityEvent, ChatMessage } from "../api";

function makeEvent(
  overrides: Partial<ActivityEvent> & { type: string },
): ActivityEvent {
  return {
    event_id: crypto.randomUUID(),
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeChat(
  role: "user" | "assistant",
  content: string,
  created_at: string,
): ChatMessage {
  return { role, content, created_at };
}

describe("buildGroups — chat interleaving", () => {
  it("empty conversation produces no chatMessages", () => {
    const events: ActivityEvent[] = [
      makeEvent({ type: "stage_transition", to: "data_gathering", created_at: "2024-01-01T00:01:00Z" }),
    ];
    const groups = buildGroups(events, [], [], null, "waiting");
    for (const g of groups) {
      expect(g.chatMessages).toHaveLength(0);
    }
  });

  it("chat message after stage_transition goes into the new group", () => {
    const events: ActivityEvent[] = [
      makeEvent({ type: "stage_transition", to: "user_review", created_at: "2024-01-01T00:02:00Z" }),
    ];
    const conversation: ChatMessage[] = [
      makeChat("assistant", "Data looks good!", "2024-01-01T00:03:00Z"),
    ];
    const groups = buildGroups(events, [], conversation, "user_review", "waiting");
    const reviewGroup = groups.find((g) => g.stage === "user_review");
    expect(reviewGroup).toBeDefined();
    expect(reviewGroup!.chatMessages).toHaveLength(1);
    expect(reviewGroup!.chatMessages[0].role).toBe("assistant");
    expect(reviewGroup!.chatMessages[0].content).toBe("Data looks good!");
  });

  it("chat message before stage_transition goes into the earlier group", () => {
    const events: ActivityEvent[] = [
      makeEvent({ type: "stage_transition", to: "user_review", created_at: "2024-01-01T00:05:00Z" }),
    ];
    const conversation: ChatMessage[] = [
      makeChat("user", "early message", "2024-01-01T00:01:00Z"),
    ];
    const groups = buildGroups(events, [], conversation, "user_review", "waiting");
    const configuringGroup = groups.find((g) => g.stage === "configuring");
    expect(configuringGroup!.chatMessages).toHaveLength(1);
    expect(configuringGroup!.chatMessages[0].content).toBe("early message");
    const reviewGroup = groups.find((g) => g.stage === "user_review");
    expect(reviewGroup!.chatMessages).toHaveLength(0);
  });

  it("user and assistant messages are ordered by timestamp within a group", () => {
    const events: ActivityEvent[] = [
      makeEvent({ type: "stage_transition", to: "user_review", created_at: "2024-01-01T00:00:00Z" }),
    ];
    const conversation: ChatMessage[] = [
      makeChat("assistant", "first", "2024-01-01T00:01:00Z"),
      makeChat("user", "second", "2024-01-01T00:02:00Z"),
      makeChat("assistant", "third", "2024-01-01T00:03:00Z"),
    ];
    const groups = buildGroups(events, [], conversation, "user_review", "waiting");
    const reviewGroup = groups.find((g) => g.stage === "user_review")!;
    expect(reviewGroup.chatMessages.map((m) => m.content)).toEqual([
      "first",
      "second",
      "third",
    ]);
  });

  it("existing tool_call/result and thought behavior is unchanged", () => {
    const wsMessages = [
      { type: "thought", content: "thinking", created_at: "2024-01-01T00:01:30Z" },
      { type: "tool_call", tool: "fetch_yfinance", input: { tickers: ["CL=F"] }, created_at: "2024-01-01T00:01:40Z" },
      { type: "tool_result", tool: "fetch_yfinance", output: { rows: 10 }, created_at: "2024-01-01T00:01:50Z" },
    ];
    const groups = buildGroups([], wsMessages, [], null, "waiting");
    expect(groups[0].thoughts).toHaveLength(1);
    expect(groups[0].fetchRows).toHaveLength(1);
    expect(groups[0].fetchRows[0].result).toEqual({ rows: 10 });
  });
});
