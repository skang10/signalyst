import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  vi.clearAllMocks();
  vi.resetModules();
});

function mockOk(data: unknown) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(""),
  });
}

function mockError(status: number, text = "error") {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    text: () => Promise.resolve(text),
  });
}

describe("api.createSession", () => {
  it("posts to /api/sessions and returns session_id", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "abc-123" });
    const result = await api.createSession({
      market_profile: "oil",
      timeframe_start: "2024-01-01",
      timeframe_end: "2024-06-30",
    });
    expect(result.session_id).toBe("abc-123");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws on API error", async () => {
    const { api } = await import("../api");
    mockError(422, "validation error");
    await expect(
      api.createSession({
        market_profile: "oil",
        timeframe_start: "2024-01-01",
        timeframe_end: "2024-06-30",
      }),
    ).rejects.toThrow("API error 422");
  });
});

describe("api.getSessions", () => {
  it("fetches /api/sessions", async () => {
    const { api } = await import("../api");
    mockOk([]);
    const result = await api.getSessions();
    expect(Array.isArray(result)).toBe(true);
  });
});

describe("api.getProfiles", () => {
  it("fetches /api/profiles", async () => {
    const { api } = await import("../api");
    mockOk([{ id: "oil", name: "Oil Markets" }]);
    const result = await api.getProfiles();
    expect(result[0].id).toBe("oil");
  });
});

describe("api.getMarketSnapshot", () => {
  it("fetches /api/market/snapshot", async () => {
    const { api } = await import("../api");
    mockOk({ wti: { price: 83.0, change_pct: 1.2 }, fetched_at: "2024-01-01T00:00:00Z" });
    const result = await api.getMarketSnapshot();
    expect(result.wti?.price).toBe(83.0);
  });
});
