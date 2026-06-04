import { TabPlaceholder } from "./TabPlaceholder";

type FeatureImportanceResult = Record<string, unknown>;
type Props = { features: FeatureImportanceResult | null };

export function FeaturesTab({ features }: Props) {
  if (!features) {
    return (
      <TabPlaceholder
        icon="≡"
        title="Feature importance not available"
        reason="Not computed in this run. Enable in Full mode or add evaluate_features to tasks."
      />
    );
  }

  const max = features.top_features[0]?.importance ?? 1;

  return (
    <div className="p-4 flex flex-col h-full">
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-4 flex flex-col gap-2 flex-1">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">
          SHAP Feature Importance
        </div>
        <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
          {features.top_features.map((f, i) => (
            <div key={f.name} className="flex items-center gap-2">
              <div className="w-32 text-right text-xs text-slate-400 font-mono truncate">
                {f.name}
              </div>
              <div className="flex-1 bg-slate-900 rounded h-3 overflow-hidden">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(f.importance / max) * 100}%`,
                    background: `linear-gradient(to right, #7c3aed, #4f46e5)`,
                    opacity: 1 - i * 0.06,
                  }}
                />
              </div>
              <div className="w-12 text-right text-xs text-slate-400 font-mono">
                {f.importance.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-slate-600 font-mono pt-2 border-t border-slate-800">
          {features.n_features_evaluated} features · {features.n_samples_explained} samples · SHAP
        </div>
      </div>
    </div>
  );
}
