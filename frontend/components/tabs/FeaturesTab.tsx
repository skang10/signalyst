import { TabPlaceholder } from "./TabPlaceholder";

type FeatureEntry = { name: string; importance: number };
type ModelInfo = { name: string; task: string; n_estimators: number };
type FeatureImportanceResult = {
  top_features: FeatureEntry[];
  n_features_evaluated: number;
  n_samples_explained: number;
  model_info?: ModelInfo;
};
type FeatureArtifactDetail = {
  n_features: number;
  n_rows: number;
  family_counts: Record<string, number>;
  featurizer_config: {
    windows: number[];
    lags: number[];
    feature_families: string[];
    energy_specific: boolean;
  };
};
type Props = {
  features: FeatureImportanceResult | null;
  featureArtifact: FeatureArtifactDetail | null;
};

function formatTaskLabel(task: string): string {
  return task
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function FamilyBar({ label, count, max }: { label: string; count: number; max: number }) {
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <div className="w-24 text-right text-gray-500 truncate">{label}</div>
      <div className="flex-1 bg-gray-100 rounded h-2 overflow-hidden">
        <div
          className="h-full rounded bg-brand"
          style={{ width: `${max > 0 ? (count / max) * 100 : 0}%` }}
        />
      </div>
      <div className="w-8 text-gray-400 text-right">{count}</div>
    </div>
  );
}

export function FeaturesTab({ features, featureArtifact }: Props) {
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
  const familyEntries = featureArtifact ? Object.entries(featureArtifact.family_counts) : [];
  const maxFamilyCount =
    familyEntries.length > 0 ? Math.max(...familyEntries.map(([, c]) => c)) : 0;

  return (
    <div className="p-4 flex flex-col gap-3 h-full overflow-y-auto">
      {features.model_info && (
        <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-1">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Model
          </div>
          <div className="text-xs text-gray-700 font-mono">
            {features.model_info.name} · {formatTaskLabel(features.model_info.task)} ·{" "}
            {features.model_info.n_estimators} ensemble members
          </div>
        </div>
      )}

      {featureArtifact && (
        <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Feature Generation
          </div>
          <div className="text-xs text-gray-700 font-mono">
            {featureArtifact.n_features} features · {featureArtifact.n_rows} rows
          </div>
          <div className="flex flex-col gap-1 mt-1">
            {familyEntries.map(([family, count]) => (
              <FamilyBar key={family} label={family} count={count} max={maxFamilyCount} />
            ))}
          </div>
          <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
            windows {featureArtifact.featurizer_config.windows.join(",")} · lags{" "}
            {featureArtifact.featurizer_config.lags.join(",")}
            {featureArtifact.featurizer_config.energy_specific ? " · energy-specific" : ""}
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-2 flex-1">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-2">
          SHAP Feature Importance
        </div>
        <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
          {features.top_features.map((f, i) => (
            <div key={f.name} className="flex items-center gap-2">
              <div className="w-32 text-right text-xs text-gray-500 font-mono truncate">
                {f.name}
              </div>
              <div className="flex-1 bg-gray-100 rounded h-3 overflow-hidden">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(f.importance / max) * 100}%`,
                    background: "var(--color-brand)",
                    opacity: 1 - i * 0.06,
                  }}
                />
              </div>
              <div className="w-12 text-right text-xs text-gray-400 font-mono">
                {f.importance.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
          {features.n_features_evaluated} features · {features.n_samples_explained} samples · SHAP
        </div>
      </div>
    </div>
  );
}
