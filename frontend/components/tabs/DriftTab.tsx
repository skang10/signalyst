import { TabPlaceholder } from "./TabPlaceholder";

type KsEntry = { statistic: number; p_value: number };
type DriftResult = {
  psi_score: number;
  drift_detected: boolean;
  drifted_features: string[];
  ks_results: Record<string, KsEntry>;
};
type Props = { drift: DriftResult | null };

function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
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
    </div>
  );
}

function psiInterpretation(psi: number, detected: boolean): string {
  if (!detected)
    return "Feature distributions are stable. The regime model is operating within its training distribution.";
  if (psi < 0.2)
    return "Moderate distributional shift detected. Monitor carefully — forecasts may be slightly less reliable than during model training.";
  return "Significant distributional shift detected. The current market regime may be outside the model's training distribution. Treat directional forecasts with higher uncertainty.";
}

export function DriftTab({ drift }: Props) {
  if (!drift) {
    return (
      <TabPlaceholder
        icon="⊘"
        title="Drift analysis not available"
        reason="Not computed in this run. Enable in Full mode or add detect_drift to tasks."
      />
    );
  }

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      <div className="grid grid-cols-3 gap-2">
        <StatTile
          label="PSI Score"
          value={drift.psi_score.toFixed(2)}
          accent={drift.drift_detected ? "text-amber-400" : "text-slate-300"}
        />
        <StatTile
          label="Drifted Features"
          value={String(drift.drifted_features.length)}
          accent={drift.drifted_features.length > 0 ? "text-amber-400" : "text-slate-300"}
        />
        <StatTile
          label="Drift Detected"
          value={drift.drift_detected ? "YES" : "NO"}
          accent={drift.drift_detected ? "text-amber-400" : "text-emerald-400"}
        />
      </div>

      <div className="bg-white border border-gray-200 rounded overflow-hidden">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest p-3 border-b border-gray-200">
          Feature KS Statistics
        </div>
        <div className="divide-y divide-gray-100">
          {Object.entries(drift.ks_results)
            .sort((a, b) => b[1].statistic - a[1].statistic)
            .map(([feature, { statistic, p_value }]) => {
              const isDrifted = drift.drifted_features.includes(feature);
              return (
                <div
                  key={feature}
                  className="flex items-center gap-3 px-3 py-2 text-xs font-mono"
                >
                  <div className="flex-1 text-gray-700 truncate">{feature}</div>
                  <div className="text-gray-400 w-12 text-right">
                    {statistic.toFixed(3)}
                  </div>
                  <div className="text-gray-400 w-12 text-right">
                    p={p_value.toFixed(3)}
                  </div>
                  <div
                    className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                      isDrifted
                        ? "bg-amber-50 text-amber-600"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {isDrifted ? "DRIFT" : "OK"}
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded p-3">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-2">
          Interpretation
        </div>
        <p className="text-xs text-gray-600 leading-relaxed">
          {psiInterpretation(drift.psi_score, drift.drift_detected)}
        </p>
      </div>
    </div>
  );
}
