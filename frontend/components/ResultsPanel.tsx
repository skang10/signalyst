"use client";

import { useRunStore } from "@/lib/store";
import { ResultsTabs } from "./ResultsTabs";

export function ResultsPanel() {
  const { status, result, error } = useRunStore();

  if (status === "idle") {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-sm text-slate-400 text-center">
          Results will appear here after analysis completes.
        </p>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <p className="text-sm text-red-400 mb-2">
            {error ?? "Analysis failed"}
          </p>
        </div>
      </div>
    );
  }

  return <ResultsTabs result={result} />;
}
