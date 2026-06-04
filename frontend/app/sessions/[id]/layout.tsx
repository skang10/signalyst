"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Results", path: "results" },
];

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const { sessionId, stage, status, setSession } = useSessionStore();

  useSessionStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    api
      .getSession(id)
      .then(setSession)
      .catch(() => router.push("/"));
  }, [id, router, setSession]);

  return (
    <div className="flex flex-col h-screen bg-[#060b14] text-[#f9fafb]">
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">■ SIGNALYST</span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-[#21262d] text-[#9ca3af] hover:text-[#f9fafb] transition-colors"
        >
          + NEW ANALYSIS
        </Link>
      </header>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <Link
          href="/"
          className="text-[#9ca3af] hover:text-[#f9fafb] text-sm transition-colors"
        >
          ← Sessions
        </Link>
        {sessionId && (
          <>
            <span className="text-[#6b7280] text-xs">·</span>
            <span className="text-sm text-[#9ca3af] font-mono">{id?.slice(0, 8)}</span>
            {stage && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#1f2937] text-[#60a5fa] border border-[#1d4ed8]">
                {stage}
              </span>
            )}
            {status && (
              <span
                className={[
                  "text-xs",
                  status === "running" ? "text-[#22c55e]" : "",
                  status === "waiting" ? "text-[#9ca3af]" : "",
                  status === "failed" ? "text-[#ef4444]" : "",
                  status === "canceled" ? "text-[#f59e0b]" : "",
                ].join(" ")}
              >
                {status === "running" && "● "}
                {status}
              </span>
            )}
          </>
        )}
      </div>

      <StageStrip currentStage={stage} />

      <div className="flex gap-4 px-4 border-b border-[#21262d] bg-[#111827]">
        {TABS.map((tab) => {
          const href = `/sessions/${id}/${tab.path}`;
          const isActive = pathname === href;
          return (
            <Link
              key={tab.label}
              href={href}
              className={[
                "text-sm py-2 border-b-2 transition-colors",
                isActive
                  ? "border-[#3b82f6] text-[#f9fafb]"
                  : "border-transparent text-[#9ca3af] hover:text-[#f9fafb]",
              ].join(" ")}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
