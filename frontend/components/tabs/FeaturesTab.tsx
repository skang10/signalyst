import { BarChart3, Cpu, Layers } from "lucide-react";
import { TabPlaceholder } from "./TabPlaceholder";
import { DashboardCard } from "./shared/DashboardCard";
import { MetricBar } from "./shared/MetricBar";
import { StatBlock } from "./shared/StatBlock";

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

const FAMILY_COLORS: Record<string, string> = {
  rolling_stats: "bg-blue-500",
  lag: "bg-purple-500",
  momentum: "bg-amber-500",
  regime: "bg-rose-500",
};

function familyColor(family: string): string {
  return FAMILY_COLORS[family] ?? "bg-gray-400";
}

function formatTaskLabel(task: string): string {
  return task
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
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
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      {features.model_info && (
        <DashboardCard icon={Cpu} title="Model">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-lg font-mono font-bold text-gray-900">
                {features.model_info.name}
              </div>
              <div className="text-xs font-mono text-gray-500">
                {formatTaskLabel(features.model_info.task)}
              </div>
            </div>
            <div className="text-xs px-2 py-0.5 rounded-full bg-brand-soft text-brand border border-brand-soft-border whitespace-nowrap">
              {features.model_info.n_estimators} ensemble members
            </div>
          </div>
        </DashboardCard>
      )}

      {featureArtifact && (
        <DashboardCard icon={Layers} title="Feature Generation">
          <div className="flex items-center gap-6">
            <StatBlock value={featureArtifact.n_features} label="features" accentClassName="text-brand" />
            <StatBlock value={featureArtifact.n_rows} label="rows" />
          </div>
          <div className="flex flex-col gap-2">
            {familyEntries.map(([family, count]) => (
              <MetricBar
                key={family}
                leading={<span className={`w-2 h-2 rounded-full ${familyColor(family)}`} />}
                label={family}
                pct={maxFamilyCount > 0 ? (count / maxFamilyCount) * 100 : 0}
                value={String(count)}
                barClassName={familyColor(family)}
              />
            ))}
          </div>
          <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
            windows {featureArtifact.featurizer_config.windows.join(",")} · lags{" "}
            {featureArtifact.featurizer_config.lags.join(",")}
            {featureArtifact.featurizer_config.energy_specific ? " · energy-specific" : ""}
          </div>
        </DashboardCard>
      )}

      <DashboardCard icon={BarChart3} title="SHAP Feature Importance" className="flex-1 min-h-0">
        <div className="flex flex-col gap-2.5 flex-1 overflow-y-auto">
          {features.top_features.map((f, i) => (
            <MetricBar
              key={f.name}
              leading={<span className="text-xs font-mono text-gray-400">{i + 1}</span>}
              label={f.name}
              pct={(f.importance / max) * 100}
              value={`${Math.round(f.importance * 100)}%`}
            />
          ))}
        </div>
        <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
          {features.n_features_evaluated} features · {features.n_samples_explained} samples · SHAP
        </div>
      </DashboardCard>
    </div>
  );
}
