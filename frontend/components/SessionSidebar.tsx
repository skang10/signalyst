"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Config", path: "config" },
  { label: "Results", path: "results" },
];

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";

export function SessionSidebar({
  sessionId,
  stage,
}: {
  sessionId: string;
  stage: string | null;
}) {
  const pathname = usePathname();

  return (
    <nav className="w-[170px] flex-shrink-0 flex flex-col gap-1 p-2.5 border-r border-[#21262d]">
      {TABS.map((tab) => {
        const href = `/sessions/${sessionId}/${tab.path}`;
        const isActive = pathname === href;

        const isLocked =
          (tab.path === "data" && stage !== null && DATA_LOCKED_STAGES.has(stage)) ||
          (tab.path === "results" && stage !== RESULTS_UNLOCKED_STAGE);

        const badge =
          tab.path === "data" && stage !== null && !DATA_LOCKED_STAGES.has(stage)
            ? " ✓"
            : tab.path === "results" && stage === RESULTS_UNLOCKED_STAGE
            ? " ✦"
            : "";

        if (isLocked) {
          return (
            <span
              key={tab.label}
              title="Locked — not available at this stage"
              className="flex items-center justify-between px-3 py-2 rounded text-sm text-[#374151] cursor-not-allowed select-none"
            >
              {tab.label}
              <span aria-hidden>🔒</span>
            </span>
          );
        }

        return (
          <Link
            key={tab.label}
            href={href}
            className={[
              "px-3 py-2 rounded text-sm transition-colors",
              isActive
                ? "bg-[#1f2937] text-[#60a5fa] font-medium"
                : "text-[#9ca3af] hover:text-[#f9fafb]",
            ].join(" ")}
          >
            {tab.label}
            {badge}
          </Link>
        );
      })}
    </nav>
  );
}
