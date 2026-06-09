import { TabPlaceholder } from "./TabPlaceholder";

type RegimeResult = {
  regime: string;
  confidence: number;
  distribution: Record<string, number>;
};
type DirectionResult = {
  direction: string;
  confidence: number;
  distribution: Record<string, number>;
};
type DriftSummary = {
  psi_score: number;
  drift_detected: boolean;
};
type FeatureImportanceSummary = {
  top_features: { name: string; importance: number }[];
};
type AnalysisResult = {
  regime?: RegimeResult | null;
  direction?: DirectionResult | null;
  drift?: DriftSummary | null;
  feature_importance?: FeatureImportanceSummary | null;
};

const REGIME_LABELS: Record<string, string> = {
  range_bound: "Range-Bound",
  bull_supercycle: "Bull Supercycle",
  bust: "Bust",
  geopolitical_spike: "Geopolitical Spike",
};

function StatTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${accent ?? "text-gray-700"}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-gray-400 font-mono">{sub}</div>}
    </div>
  );
}

function DistBar({
  label,
  pct,
  color,
}: {
  label: string;
  pct: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <div className="w-28 text-right text-gray-500 truncate">{label}</div>
      <div className="flex-1 bg-gray-100 rounded h-2 overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-8 text-gray-400 text-right">{pct.toFixed(0)}%</div>
    </div>
  );
}

type Props = { result: AnalysisResult };

export function OverviewTab({ result }: Props) {
  const { regime, direction, drift, feature_importance } = result;

  if (!regime || !direction) {
    return (
      <TabPlaceholder
        icon="▦"
        title="Analysis incomplete"
        reason="Regime or direction result missing — the run may have failed mid-way."
      />
    );
  }

  const regimeTotal = Object.values(regime.distribution).reduce((s, v) => s + v, 0);
  const directionTotal = Object.values(direction.distribution).reduce((s, v) => s + v, 0);

  const psiSeverity =
    drift == null
      ? "No data"
      : drift.psi_score < 0.1
      ? "Stable"
      : drift.psi_score < 0.2
      ? "Moderate"
      : "High";

  const topSignalName = feature_importance?.top_features[0]?.name ?? "—";
  const topSignalScore = feature_importance?.top_features[0]?.importance;

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatTile
          label="Regime"
          value={REGIME_LABELS[regime.regime] ?? regime.regime}
          sub={`${(regime.confidence * 100).toFixed(1)}% confidence`}
          accent="text-teal-600"
        />
        <StatTile
          label="WTI Direction"
          value={direction.direction === "up" ? "▲ Up" : "▼ Down"}
          sub={`${(direction.confidence * 100).toFixed(1)}% confidence`}
          accent={direction.direction === "up" ? "text-emerald-400" : "text-red-400"}
        />
        <StatTile
          label="Drift"
          value={drift ? drift.psi_score.toFixed(2) : "—"}
          sub={psiSeverity}
          accent={drift?.drift_detected ? "text-amber-400" : "text-slate-400"}
        />
        <StatTile
          label="Top Signal"
          value={topSignalName}
          sub={topSignalScore != null ? `SHAP ${topSignalScore.toFixed(2)}` : undefined}
          accent="text-teal-600"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Regime Distribution
          </div>
          {Object.entries(regime.distribution)
            .sort((a, b) => b[1] - a[1])
            .map(([r, count]) => (
              <DistBar
                key={r}
                label={REGIME_LABELS[r] ?? r}
                pct={regimeTotal > 0 ? (count / regimeTotal) * 100 : 0}
                color={
                  r === "bull_supercycle"
                    ? "bg-emerald-600"
                    : r === "bust"
                    ? "bg-red-600"
                    : r === "geopolitical_spike"
                    ? "bg-amber-500"
                    : "bg-teal-600"
                }
              />
            ))}
        </div>

        <div className="bg-white border border-gray-200 rounded p-3 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Direction Distribution
          </div>
          {Object.entries(direction.distribution)
            .sort((a, b) => b[1] - a[1])
            .map(([d, count]) => (
              <DistBar
                key={d}
                label={d === "up" ? "▲ Up" : "▼ Down"}
                pct={directionTotal > 0 ? (count / directionTotal) * 100 : 0}
                color={d === "up" ? "bg-emerald-600" : "bg-red-600"}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
