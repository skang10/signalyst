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

describe("api.proceed", () => {
  it("posts to /proceed with no body when no patch is given", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    await api.proceed("ses-1");
    const [, init] = mockFetch.mock.calls[0];
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/ses-1/proceed"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(init.body).toBeUndefined();
  });

  it("posts featurizer_config_patch in the body when a patch is given", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    const patch = {
      windows: [5, 30, 90],
      lags: [1, 5],
      feature_families: ["rolling_stats"],
      energy_specific: true,
    };
    await api.proceed("ses-1", patch);
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({ featurizer_config_patch: patch });
  });
});

describe("api.updateConfig", () => {
  it("PATCHes /config with the featurizer_config_patch body", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    const patch = { featurizer_config_patch: { windows: [7, 30, 90] } };
    await api.updateConfig("ses-1", patch);
    const [, init] = mockFetch.mock.calls[0];
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/ses-1/config"),
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(JSON.parse(init.body as string)).toEqual(patch);
  });
});

describe("api.cancelSession", () => {
  it("posts to /cancel and returns status", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1", stage: "featurizing", status: "canceled" });
    const result = await api.cancelSession("ses-1");
    expect(result.status).toBe("canceled");
  });
});

describe("api.getArtifact", () => {
  it("fetches artifact detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "data",
      artifact_id: "art-1",
      round: 1,
      sources: [],
      data_manifest: {
        tickers: ["CL=F"],
        rows: 100,
        date_range: { start: "2023-01-01", end: "2023-06-30" },
        missing_pct: {},
        summary_stats: {},
      },
      series_preview: { "CL=F": [{ date: "2023-01-01", value: 78.4 }] },
      cache_hit: false,
      cached_from_session_id: null,
    });
    const result = await api.getArtifact("ses-1", "art-1");
    expect(result.kind).toBe("data");
    expect(result.artifact_id).toBe("art-1");
  });
});

describe("api.getAnalysisArtifact", () => {
  it("fetches analysis result detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "analysis",
      artifact_id: "ar-1",
      regime: { regime: "bull_supercycle", confidence: 0.8, distribution: { bull_supercycle: 10 } },
      direction: { direction: "up", confidence: 0.7, distribution: { up: 8, down: 2 } },
      feature_importance: {
        top_features: [{ name: "CL=F_ret_5", importance: 0.42 }],
        n_features_evaluated: 12,
        n_samples_explained: 20,
      },
      drift: { psi_score: 0.05, drift_detected: false },
      backtest: { strategy_sharpe: 1.2, benchmark_sharpe: 0.8, regime_accuracy: 0.65, n_windows: 5 },
      summary: "Markets are in a bull supercycle.",
      cache_hit: false,
      cached_from_session_id: null,
    });
    const result = await api.getAnalysisArtifact("ses-1", "ar-1");
    expect(result.kind).toBe("analysis");
    expect(result.regime?.regime).toBe("bull_supercycle");
    expect(result.feature_importance?.top_features[0].name).toBe("CL=F_ret_5");
    expect(result.backtest?.strategy_sharpe).toBe(1.2);
  });
});

describe("api.getFeatureArtifact", () => {
  it("fetches feature artifact detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "features",
      artifact_id: "fa-1",
      n_features: 108,
      n_rows: 22,
      family_counts: { rolling_stats: 48, lag: 30, momentum: 30 },
      columns: ["CL=F_mean_5d"],
      featurizer_config: {
        windows: [5, 20, 60],
        lags: [1, 5, 20],
        feature_families: ["rolling_stats", "lag", "momentum"],
        energy_specific: true,
      },
      cache_hit: false,
      created_at: "2026-06-22T00:00:00",
    });
    const result = await api.getFeatureArtifact("ses-1", "fa-1");
    expect(result.kind).toBe("features");
    expect(result.n_features).toBe(108);
    expect(result.family_counts.rolling_stats).toBe(48);
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
