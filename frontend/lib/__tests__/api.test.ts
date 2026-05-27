import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api } from "../api";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function mockResponse(body: object, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

describe("api.getRun", () => {
  it("returns parsed JSON on success", async () => {
    mockResponse({ run_id: "abc", status: "completed", result: null });
    const result = await api.getRun("abc");
    expect(result.run_id).toBe("abc");
    expect(result.status).toBe("completed");
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      text: () => Promise.resolve("not found"),
    });
    await expect(api.getRun("missing")).rejects.toThrow("API error 404");
  });
});

describe("api.analyze", () => {
  it("sends POST with correct body", async () => {
    mockResponse({ run_id: "xyz" });
    await api.analyze({ date_range_start: "2020-01-01", date_range_end: "2024-01-01" });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/analyze"),
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("request timeout", () => {
  it("aborts after 30s", async () => {
    mockFetch.mockImplementationOnce(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        })
    );

    const promise = api.getRun("slow");
    vi.advanceTimersByTime(30_001);
    await expect(promise).rejects.toThrow();
  });
});
