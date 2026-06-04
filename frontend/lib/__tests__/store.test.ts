import { beforeEach, describe, expect, it } from "vitest";
import { useSessionStore } from "../store";
import type { Session } from "../api";

function mockSession(overrides: Partial<Session> = {}): Session {
  return {
    session_id: "ses-1",
    market_profile: "oil",
    timeframe_start: "2024-01-01",
    timeframe_end: "2024-06-30",
    stage: "configuring",
    status: "waiting",
    error: null,
    auto: false,
    featurizer_config: {
      windows: [5, 20, 60],
      lags: [1, 5, 20],
      feature_families: [],
      energy_specific: true,
    },
    conversation: [],
    activity_events: [],
    stage_history: [],
    artifacts: { data: [], features: [], analysis: [] },
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  useSessionStore.getState().clearSession();
});

describe("useSessionStore", () => {
  it("starts with null sessionId", () => {
    expect(useSessionStore.getState().sessionId).toBeNull();
  });

  it("setSession populates store from session object", () => {
    useSessionStore.getState().setSession(mockSession());
    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("ses-1");
    expect(state.stage).toBe("configuring");
    expect(state.status).toBe("waiting");
    expect(state.error).toBeNull();
  });

  it("clearSession resets all fields", () => {
    useSessionStore.getState().setSession(mockSession());
    useSessionStore.getState().clearSession();
    const state = useSessionStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.stage).toBeNull();
    expect(state.wsMessages).toEqual([]);
  });

  it("appendWsMessage adds to wsMessages", () => {
    useSessionStore.getState().appendWsMessage({ type: "thought", content: "thinking" });
    expect(useSessionStore.getState().wsMessages).toHaveLength(1);
    expect(useSessionStore.getState().wsMessages[0].type).toBe("thought");
  });

  it("appendWsMessage caps at 500 messages", () => {
    for (let i = 0; i < 510; i++) {
      useSessionStore.getState().appendWsMessage({ type: "thought", content: `msg ${i}` });
    }
    expect(useSessionStore.getState().wsMessages).toHaveLength(500);
  });
});
