"use client";

import { useState } from "react";
import type { AnalysisResult } from "../lib/api";
import { useRunStore } from "@/lib/store";
import { AgentDrawer } from "./AgentDrawer";
import { OverviewTab } from "./tabs/OverviewTab";
import { FeaturesTab } from "./tabs/FeaturesTab";
import { DriftTab } from "./tabs/DriftTab";
import { BacktestTab } from "./tabs/BacktestTab";
import { SummaryTab } from "./tabs/SummaryTab";

type TabId = "overview" | "features" | "drift" | "backtest" | "summary";

const TABS: Array<{ id: TabId; label: string; icon: string }> = [
  { id: "overview", label: "Overview", icon: "▦" },
  { id: "features", label: "Features", icon: "≡" },
  { id: "drift", label: "Drift", icon: "⊘" },
  { id: "backtest", label: "Backtest", icon: "↗" },
  { id: "summary", label: "Summary", icon: "✎" },
];

type Props = { result: AnalysisResult | null };

function WaitingForResults() {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-sm rounded border border-slate-800 bg-[#0d0d18] px-6 py-5 text-center">
        <div className="text-sm font-semibold text-slate-300">Waiting for results</div>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          This tab will update when the agent finishes the relevant step.
        </p>
      </div>
    </div>
  );
}

export function ResultsTabs({ result }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  // Keyed to `status` so user overrides reset when status transitions.
  const [manualOpen, setManualOpen] = useState<{ forStatus: string; value: boolean } | null>(null);
  const { status } = useRunStore();

  const drawerOpen = manualOpen?.forStatus === status ? manualOpen.value : status === "running";

  function toggleDrawer() {
    setManualOpen({ forStatus: status, value: !drawerOpen });
  }

  function renderTab() {
    if (!result) {
      return <WaitingForResults />;
    }
    switch (activeTab) {
      case "overview":
        return <OverviewTab result={result} />;
      case "features":
        return <FeaturesTab features={result.feature_importance} />;
      case "drift":
        return <DriftTab drift={result.drift} />;
      case "backtest":
        return <BacktestTab backtest={result.backtest} />;
      case "summary":
        return <SummaryTab summary={result.summary} />;
    }
  }

  return (
    <div className="flex h-full">
      {/* Icon sidebar */}
      <div className="w-10 flex flex-col items-center py-3 gap-1 border-r border-slate-800 bg-[#07070f] shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            aria-label={`${tab.label} sidebar`}
            title={tab.label}
            onClick={() => setActiveTab(tab.id)}
            className={`w-8 h-8 flex items-center justify-center rounded text-sm transition-colors ${
              activeTab === tab.id
                ? "bg-violet-950 text-violet-400"
                : "text-slate-600 hover:text-slate-400 hover:bg-slate-800"
            }`}
          >
            {tab.icon}
          </button>
        ))}
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Tab bar */}
        <div className="flex border-b border-slate-800 bg-[#07070f] shrink-0 items-center">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              aria-label={`${tab.icon} ${tab.label}`}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 text-xs font-mono transition-colors border-b-2 ${
                activeTab === tab.id
                  ? "border-violet-500 text-violet-400"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
          {status !== "idle" && (
            <button
              aria-label={drawerOpen ? "Collapse agent drawer" : "Expand agent drawer"}
              onClick={toggleDrawer}
              className={`ml-auto mr-2 px-2 py-1 text-xs font-mono rounded border ${
                status === "running"
                  ? "border-violet-800 text-violet-400 animate-pulse"
                  : "border-slate-700 text-slate-500"
              }`}
            >
              ◎ Agent {drawerOpen ? "▸" : "◂"}
            </button>
          )}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden bg-[#07070f]">{renderTab()}</div>
      </div>
      <AgentDrawer isOpen={drawerOpen} />
    </div>
  );
}
