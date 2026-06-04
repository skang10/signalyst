import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() {
    this.readyState = 3;
  }
}

vi.stubGlobal("WebSocket", MockWebSocket);
vi.stubGlobal(
  "fetch",
  vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
);

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.resetModules();
});

describe("useSessionStream", () => {
  it("connects to the correct session WS URL", async () => {
    const { useSessionStream } = await import("../websocket");
    renderHook(() => useSessionStream("ses-abc"));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain("/ws/sessions/ses-abc/stream");
  });

  it("does not connect when sessionId is null", async () => {
    const { useSessionStream } = await import("../websocket");
    renderHook(() => useSessionStream(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });
});
