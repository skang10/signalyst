"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { SessionSidebar } from "@/components/SessionSidebar";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { sessionId, stage, status, setSession } = useSessionStore();
  const [canceling, setCanceling] = useState(false);

  useSessionStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    api
      .getSession(id)
      .then(setSession)
      .catch(() => router.push("/"));
  }, [id, router, setSession]);

  useEffect(() => {
    if (!id || status !== "running") return;
    const interval = setInterval(() => {
      api.getSession(id).then(setSession).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [id, status, setSession]);

  const handleCancel = async () => {
    if (!id) return;
    setCanceling(true);
    try {
      await api.cancelSession(id);
      const updated = await api.getSession(id);
      setSession(updated);
    } catch {
      // swallow — status will update on next poll/WS event
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <span className="font-bold text-gray-900 text-base tracking-tight">■ Signalyst</span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-gray-200 text-gray-500 hover:text-gray-900 transition-colors"
        >
          + New Analysis
        </Link>
      </header>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white">
        <Link href="/" className="text-gray-500 hover:text-gray-900 text-sm transition-colors">
          ← Sessions
        </Link>
        {sessionId && (
          <>
            <span className="text-gray-300 text-xs">·</span>
            <span className="text-sm text-gray-500 font-mono">{id?.slice(0, 8)}</span>
            {stage && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-brand-soft text-brand border border-brand-soft-border">
                {stage}
              </span>
            )}
            {status && (
              <span
                className={[
                  "text-xs",
                  status === "running" ? "text-green-600" : "",
                  status === "waiting" ? "text-gray-500" : "",
                  status === "failed" ? "text-red-500" : "",
                  status === "canceled" ? "text-amber-500" : "",
                ].join(" ")}
              >
                {status === "running" && "● "}
                {status}
              </span>
            )}
            {status === "running" && (
              <button
                onClick={handleCancel}
                disabled={canceling}
                className="ml-auto text-xs px-2 py-0.5 rounded border border-red-400 text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40"
              >
                {canceling ? "Canceling…" : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>

      <div className="flex-1 min-h-0 m-4 flex border border-gray-200 rounded-lg overflow-hidden bg-white">
        {id && <SessionSidebar sessionId={id} stage={stage} />}
        <div className="flex-1 flex flex-col min-h-0">
          <StageStrip currentStage={stage} />
          <main className="flex-1 overflow-auto min-h-0">{children}</main>
        </div>
      </div>
    </div>
  );
}
