"use client";

import { useEffect, useState } from "react";
import { NewAnalysisModal } from "@/components/NewAnalysisModal";
import { SessionIndicators } from "@/components/SessionIndicators";
import { SessionsTable } from "@/components/SessionsTable";
import { api } from "@/lib/api";
import type { SessionListItem } from "@/lib/api";

export default function Home() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [showModal, setShowModal] = useState(false);

  const refresh = () => {
    api.getSessions().then(setSessions).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-white text-gray-900">
      <header className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <span className="font-bold text-gray-900 text-base tracking-tight">■ Signalyst</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowModal(true)}
            className="text-sm px-3 py-1 rounded bg-brand hover:bg-brand-hover text-white font-semibold transition-colors"
          >
            + New Analysis
          </button>
        </div>
      </header>

      <SessionIndicators />

      <main className="flex-1 px-4 py-4">
        <h1 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Sessions</h1>
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <SessionsTable sessions={sessions} onDelete={refresh} />
        </div>
      </main>

      {showModal && (
        <NewAnalysisModal
          onClose={() => {
            setShowModal(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
