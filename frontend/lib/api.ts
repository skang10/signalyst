const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30_000;

export type RunStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export type AnalyzeRequest = {
  date_range_start: string;
  date_range_end: string;
  tasks?: string[];
  analysis_mode?: "quick" | "full";
  pre_messages: string[];
};

export type RegimeResult = {
  regime: string;
  confidence: number;
  entropy: number;
  distribution: Record<string, number>;
};

export type DirectionResult = {
  direction: string;
  confidence: number;
  entropy: number;
  prediction_date: string;
  distribution: Record<string, number>;
};

export type DriftResult = {
  drift_detected: boolean;
  psi_score: number;
  drifted_features: string[];
  ks_results: Record<string, { statistic: number; p_value: number }>;
};

export type FeatureImportanceResult = {
  top_features: Array<{ name: string; importance: number }>;
  n_features_evaluated: number;
  n_samples_explained: number;
};

export type BacktestResult = {
  regime_accuracy: number;
  strategy_sharpe: number;
  benchmark_sharpe: number;
  n_windows: number;
};

export type AnalysisResult = {
  regime: RegimeResult | null;
  direction: DirectionResult | null;
  drift: DriftResult | null;
  feature_importance: FeatureImportanceResult | null;
  backtest: BacktestResult | null;
  summary: string;
  usage: { input_tokens: number; output_tokens: number; estimated_cost_usd: number };
  data_manifest: unknown;
};

export type RunResult = {
  run_id: string;
  status: RunStatus;
  result: AnalysisResult | null;
};

export type HistoryItem = {
  run_id: string;
  created_at: string;
  regime: string | null;
  status: RunStatus;
};

export type DerivativesPriceRequest = {
  regime: string;
  spot: number;
  strike: number;
  tenor_days: number;
  option_type?: "call" | "put";
  style?: "european" | "american";
  n_paths?: number;
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

export const api = {
  analyze: (body: AnalyzeRequest) =>
    request<{ run_id: string }>("/api/analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRun: (runId: string) =>
    request<RunResult>(`/api/runs/${runId}`),

  cancelRun: (runId: string) =>
    request<{ run_id: string; status: RunStatus }>(`/api/runs/${runId}/cancel`, {
      method: "POST",
    }),

  getHistory: () =>
    request<HistoryItem[]>("/api/history"),

  priceDerivative: (body: DerivativesPriceRequest) =>
    request("/api/derivatives/price", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
