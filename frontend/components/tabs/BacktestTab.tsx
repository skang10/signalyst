import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { TabPlaceholder } from "./TabPlaceholder";

type BacktestResult = Record<string, unknown>;
type Props = { backtest: BacktestResult | null };

function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="bg-[#0d0d18] border border-slate-800 rounded p-3 flex flex-col gap-1">
      <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">
        {label}
      </div>
      <div className={`text-2xl font-mono font-bold ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}

export function BacktestTab({ backtest }: Props) {
  if (!backtest) {
    return (
      <TabPlaceholder
        icon="↗"
        title="Backtest not available"
        reason="Not run in quick mode. Switch to Full mode to enable walk-forward evaluation."
      />
    );
  }

  const chartData = [
    {
      name: "Sharpe Ratio",
      Strategy: +backtest.strategy_sharpe.toFixed(2),
      Benchmark: +backtest.benchmark_sharpe.toFixed(2),
    },
  ];

  return (
    <div className="p-4 flex flex-col gap-4 h-full overflow-y-auto">
      <div className="grid grid-cols-3 gap-2">
        <MetricTile
          label="Regime Accuracy"
          value={`${(backtest.regime_accuracy * 100).toFixed(1)}%`}
          accent="text-violet-400"
        />
        <MetricTile
          label="Strategy Sharpe"
          value={backtest.strategy_sharpe.toFixed(2)}
          accent={
            backtest.strategy_sharpe > backtest.benchmark_sharpe
              ? "text-emerald-400"
              : "text-slate-300"
          }
        />
        <MetricTile
          label="Benchmark Sharpe"
          value={backtest.benchmark_sharpe.toFixed(2)}
          accent="text-slate-400"
        />
      </div>

      <div className="bg-[#0d0d18] border border-slate-800 rounded p-4 flex-1 min-h-[180px]">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-3">
          Strategy vs Benchmark Sharpe
        </div>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={chartData} barCategoryGap="40%">
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: "#475569", fontFamily: "monospace" }}
            />
            <YAxis tick={{ fontSize: 10, fill: "#475569", fontFamily: "monospace" }} />
            <Tooltip
              contentStyle={{
                background: "#0d0d18",
                border: "1px solid #1e293b",
                borderRadius: 4,
                fontSize: 11,
                fontFamily: "monospace",
              }}
            />
            <Legend wrapperStyle={{ fontSize: 10, fontFamily: "monospace" }} />
            <Bar dataKey="Strategy" fill="#7c3aed" radius={[2, 2, 0, 0]} />
            <Bar dataKey="Benchmark" fill="#475569" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="text-[10px] text-slate-600 font-mono mt-2">
          {backtest.n_windows} windows · walk-forward evaluation
        </div>
      </div>
    </div>
  );
}
