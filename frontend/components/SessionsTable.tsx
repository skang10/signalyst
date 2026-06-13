"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
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
  running: "bg-green-500 animate-pulse",
  waiting: "bg-gray-400",
  failed: "bg-red-500",
  canceled: "bg-amber-500",
};

type Props = { sessions: SessionListItem[]; onDelete: () => void };

export function SessionsTable({ sessions, onDelete }: Props) {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm("Delete this session? This cannot be undone.")) return;
    setDeletingId(sessionId);
    try {
      await api.deleteSession(sessionId);
      onDelete();
    } catch {
      // swallow — row stays visible if delete fails
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSelected = (sessionId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((prev) =>
      prev.size === sessions.length ? new Set() : new Set(sessions.map((s) => s.session_id))
    );
  };

  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selected.size} session(s)? This cannot be undone.`)) return;
    setBulkDeleting(true);
    try {
      await Promise.all([...selected].map((id) => api.deleteSession(id)));
      setSelected(new Set());
      onDelete();
    } catch {
      // swallow — rows that failed to delete stay visible
    } finally {
      setBulkDeleting(false);
    }
  };

  if (sessions.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
        No sessions yet — create your first analysis above
      </div>
    );
  }

  return (
    <>
      {selected.size > 0 && (
        <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200 text-sm">
          <span className="text-gray-500">{selected.size} selected</span>
          <button
            onClick={handleBulkDelete}
            disabled={bulkDeleting}
            className="text-red-500 hover:text-red-600 text-xs transition-colors disabled:opacity-40"
          >
            {bulkDeleting ? "Deleting…" : "Delete selected"}
          </button>
        </div>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 text-xs uppercase tracking-wider">
            <th className="px-4 py-2 w-8">
              <input
                type="checkbox"
                checked={selected.size === sessions.length}
                onChange={toggleSelectAll}
                aria-label="Select all sessions"
              />
            </th>
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
              className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
            >
              <td className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={selected.has(s.session_id)}
                  onChange={() => toggleSelected(s.session_id)}
                  aria-label={`Select session ${s.session_id}`}
                />
              </td>
              <td className="px-4 py-3 text-gray-900 font-medium capitalize">{s.market_profile}</td>
              <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                {s.timeframe_start} → {s.timeframe_end}
              </td>
              <td className="px-4 py-3">
                <span className="text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-600 border border-teal-200">
                  {STAGE_LABELS[s.stage] ?? s.stage}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${STATUS_DOT[s.status]}`} />
                  <span className="text-gray-500 capitalize">{s.status}</span>
                </div>
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs">
                {new Date(s.updated_at).toLocaleString()}
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-3">
                  <Link
                    href={`/sessions/${s.session_id}/activity`}
                    className="text-teal-600 hover:text-teal-700 text-xs transition-colors"
                  >
                    Open →
                  </Link>
                  <button
                    onClick={() => handleDelete(s.session_id)}
                    disabled={deletingId === s.session_id}
                    className="text-gray-400 hover:text-red-500 text-xs transition-colors disabled:opacity-40"
                    aria-label="Delete session"
                  >
                    {deletingId === s.session_id ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
