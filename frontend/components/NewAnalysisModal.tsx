"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { MarketProfile } from "@/lib/api";

type Props = { onClose: () => void };

export function NewAnalysisModal({ onClose }: Props) {
  const router = useRouter();
  const [profiles, setProfiles] = useState<MarketProfile[]>([]);
  const [profileId, setProfileId] = useState("oil");
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [autoMode, setAutoMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getProfiles().then(setProfiles).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await api.createSession({
        market_profile: profileId,
        timeframe_start: start,
        timeframe_end: end,
        auto: autoMode,
      });
      router.push(`/sessions/${session_id}/activity`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-white border border-gray-200 rounded-lg p-6 w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">New Analysis</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-lg"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-gray-500 uppercase tracking-wider">Market Profile</span>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              {profiles.length === 0 && <option value="oil">Oil Markets</option>}
            </select>
          </label>

          <div className="flex gap-3">
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-gray-500 uppercase tracking-wider">Start</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-gray-500 uppercase tracking-wider">End</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand"
              />
            </label>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoMode}
              onChange={(e) => setAutoMode(e.target.checked)}
              className="w-4 h-4 accent-brand"
            />
            <span className="text-sm text-gray-500">Auto mode (skip user review gate)</span>
          </label>

          {error && <p className="text-xs text-red-500">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 py-2 rounded bg-brand hover:bg-brand-hover disabled:opacity-50 text-sm font-semibold text-white transition-colors"
          >
            {loading ? "Starting…" : "Start Analysis"}
          </button>
        </form>
      </div>
    </div>
  );
}
