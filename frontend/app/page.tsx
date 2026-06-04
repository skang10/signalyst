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
    <div className="flex flex-col min-h-screen bg-[#060b14] text-[#f9fafb]">
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">■ SIGNALYST</span>
        <button
          onClick={() => setShowModal(true)}
          className="text-sm px-3 py-1 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white font-semibold transition-colors"
        >
          + NEW ANALYSIS
        </button>
      </header>

      <SessionIndicators />

      <main className="flex-1 px-4 py-4">
        <h1 className="text-xs text-[#6b7280] uppercase tracking-wider mb-3">Sessions</h1>
        <div className="rounded-lg border border-[#21262d] overflow-hidden">
          <SessionsTable sessions={sessions} />
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
