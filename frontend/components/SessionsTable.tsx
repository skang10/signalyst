"use client";

import Link from "next/link";
import type { SessionListItem, SessionStage, SessionStatus } from "@/lib/api";

const STAGE_LABELS: Record<SessionStage, string> = {
  configuring: "Config",
  data_gathering: "Data",
  user_review: "Review",
  featurizing: "Features",
  analyzing: "Analyze",
  explaining: "Explain",
  follow_up: "Follow-up",
};

const STATUS_DOT: Record<SessionStatus, string> = {
  running: "bg-[#22c55e] animate-pulse",
  waiting: "bg-[#9ca3af]",
  failed: "bg-[#ef4444]",
  canceled: "bg-[#f59e0b]",
};

type Props = { sessions: SessionListItem[] };

export function SessionsTable({ sessions }: Props) {
  if (sessions.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-[#6b7280] text-sm">
        No sessions yet — create your first analysis above
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-[#21262d] text-[#6b7280] text-xs uppercase tracking-wider">
          <th className="text-left px-4 py-2">Profile</th>
          <th className="text-left px-4 py-2">Timeframe</th>
          <th className="text-left px-4 py-2">Stage</th>
          <th className="text-left px-4 py-2">Status</th>
          <th className="text-left px-4 py-2">Last Updated</th>
          <th className="px-4 py-2" />
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr
            key={s.session_id}
            className="border-b border-[#1f2937] hover:bg-[#111827] transition-colors"
          >
            <td className="px-4 py-3 text-[#f9fafb] font-medium capitalize">{s.market_profile}</td>
            <td className="px-4 py-3 text-[#9ca3af] font-mono text-xs">
              {s.timeframe_start} → {s.timeframe_end}
            </td>
            <td className="px-4 py-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#1f2937] text-[#60a5fa] border border-[#1d4ed8]">
                {STAGE_LABELS[s.stage] ?? s.stage}
              </span>
            </td>
            <td className="px-4 py-3">
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${STATUS_DOT[s.status]}`} />
                <span className="text-[#9ca3af] capitalize">{s.status}</span>
              </div>
            </td>
            <td className="px-4 py-3 text-[#6b7280] text-xs">
              {new Date(s.updated_at).toLocaleString()}
            </td>
            <td className="px-4 py-3 text-right">
              <Link
                href={`/sessions/${s.session_id}/activity`}
                className="text-[#3b82f6] hover:text-[#60a5fa] text-xs transition-colors"
              >
                Open →
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
