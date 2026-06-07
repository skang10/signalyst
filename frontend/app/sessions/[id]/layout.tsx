"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { SessionSidebar } from "@/components/SessionSidebar";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

function ReviewBanner({ sessionId }: { sessionId: string }) {
  const { conversation, status } = useSessionStore();
  const pathname = usePathname();
  const activityHref = `/sessions/${sessionId}/activity`;

  if (pathname === activityHref) return null;

  const lastMsg = conversation[conversation.length - 1];
  const hasAgentReply = lastMsg?.role === "assistant";

  let hint: string;
  let linkText: string;
  if (status === "running") {
    hint = "· Agent is thinking…";
    linkText = "view in Activity →";
  } else if (hasAgentReply) {
    hint = "· Agent replied —";
    linkText = "go to Activity to respond →";
  } else {
    hint = "· Satisfied with the data?";
    linkText = "Go to Activity to proceed →";
  }

  return (
    <div className="flex items-center gap-2 px-4 py-1.5 bg-[#0a1628] border-b border-[#1d4ed8] text-xs flex-shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-pulse flex-shrink-0" />
      <span className="text-[#93c5fd]">{hint}</span>
      <Link href={activityHref} className="text-[#3b82f6] underline underline-offset-2">
        {linkText}
      </Link>
    </div>
  );
}

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
        <Link href="/" className="text-[#9ca3af] hover:text-[#f9fafb] text-sm transition-colors">
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
            {status === "running" && (
              <button
                onClick={handleCancel}
                disabled={canceling}
                className="ml-auto text-xs px-2 py-0.5 rounded border border-[#ef4444] text-[#ef4444] hover:bg-[#ef4444] hover:text-white transition-colors disabled:opacity-40"
              >
                {canceling ? "Canceling…" : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>

      <StageStrip currentStage={stage} />

      {stage === "user_review" && id && <ReviewBanner sessionId={id} />}

      <div className="flex-1 min-h-0 m-4 flex border border-[#21262d] rounded-lg overflow-hidden">
        {id && <SessionSidebar sessionId={id} stage={stage} />}
        <main className="flex-1 overflow-auto min-h-0">{children}</main>
      </div>
    </div>
  );
}
