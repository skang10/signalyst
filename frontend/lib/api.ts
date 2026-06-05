const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30_000;

export type SessionStage =
  | "configuring"
  | "data_gathering"
  | "user_review"
  | "featurizing"
  | "analyzing"
  | "explaining"
  | "follow_up";

export type SessionStatus = "running" | "waiting" | "failed" | "canceled";

export type FeaturizerConfig = {
  windows: number[];
  lags: number[];
  feature_families: string[];
  energy_specific: boolean;
};

export type DataArtifactRef = {
  artifact_id: string;
  round: number;
  cache_hit: boolean;
  created_at: string;
};

export type FeatureArtifactRef = {
  artifact_id: string;
  cache_hit: boolean;
  created_at: string;
};

export type AnalysisResultRef = {
  artifact_id: string;
  cache_hit: boolean;
  has_summary: boolean;
  created_at: string;
};

export type SessionArtifacts = {
  data: DataArtifactRef[];
  features: FeatureArtifactRef[];
  analysis: AnalysisResultRef[];
};

export type ChatMessage = {
  role: "user" | "agent";
  content: string;
  created_at: string;
};

export type ActivityEvent = {
  event_id: string;
  type: string;
  created_at: string;
  [key: string]: unknown;
};

export type StageHistoryEntry = {
  stage: SessionStage;
  entered_at: string;
};

export type Session = {
  session_id: string;
  market_profile: string;
  timeframe_start: string;
  timeframe_end: string;
  stage: SessionStage;
  status: SessionStatus;
  error: string | null;
  auto: boolean;
  featurizer_config: FeaturizerConfig;
  conversation: ChatMessage[];
  activity_events: ActivityEvent[];
  stage_history: StageHistoryEntry[];
  artifacts: SessionArtifacts;
  created_at: string;
  updated_at: string;
};

export type SessionListItem = {
  session_id: string;
  market_profile: string;
  timeframe_start: string;
  timeframe_end: string;
  stage: SessionStage;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
};

export type MarketProfile = {
  id: string;
  name: string;
  description: string;
  default_connectors: string[];
  default_featurizer_config: FeaturizerConfig;
  regime_labels: string[];
};

export type MarketSnapshot = {
  wti: { price: number; change_pct: number } | null;
  brent: { price: number; change_pct: number } | null;
  dxy: { price: number; change_pct: number } | null;
  gpr: { value: number; change_pct: number } | null;
  eia_inventory_change_mmbbl: number | null;
  fetched_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}

export type DataArtifactDetail = {
  kind: "data";
  artifact_id: string;
  round: number;
  sources: unknown[];
  data_manifest: {
    tickers: string[];
    date_range: { start: string; end: string };
    rows: number;
    missing_pct: Record<string, number>;
    summary_stats: Record<string, { mean: number; std: number; min: number; max: number }>;
    warnings?: string[];
  };
  series_preview: Record<string, { date: string; value: number | null }[]>;
  cache_hit: boolean;
  cached_from_session_id: string | null;
};

export const api = {
  getMarketSnapshot: () => request<MarketSnapshot>("/api/market/snapshot"),

  createSession: (body: {
    market_profile: string;
    timeframe_start: string;
    timeframe_end: string;
    auto?: boolean;
  }) =>
    request<{ session_id: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSessions: () => request<SessionListItem[]>("/api/sessions"),

  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),

  deleteSession: (id: string) =>
    request<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  getProfiles: () => request<MarketProfile[]>("/api/profiles"),

  proceed: (sessionId: string) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/proceed`, { method: "POST" }),

  rerun: (
    sessionId: string,
    stage: string,
    featurizerConfigPatch?: Record<string, unknown>,
  ) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/rerun`, {
      method: "POST",
      body: JSON.stringify({
        stage,
        featurizer_config_patch: featurizerConfigPatch ?? null,
      }),
    }),

  cancelSession: (sessionId: string) =>
    request<{ session_id: string; stage: string; status: string }>(
      `/api/sessions/${sessionId}/cancel`,
      { method: "POST" },
    ),

  uploadData: (sessionId: string, file: File, sourceName: string): Promise<{ artifact_id: string }> => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_name", sourceName);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    return fetch(`${API_URL}/api/sessions/${sessionId}/upload`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    })
      .then((res) => {
        clearTimeout(timeout);
        if (!res.ok) throw new Error(`API error ${res.status}`);
        return res.json() as Promise<{ artifact_id: string }>;
      })
      .catch((err) => {
        clearTimeout(timeout);
        throw err;
      });
  },

  getArtifact: (sessionId: string, artifactId: string) =>
    request<DataArtifactDetail>(`/api/sessions/${sessionId}/artifacts/${artifactId}`),
};
