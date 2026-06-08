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
    <nav className="w-[170px] flex-shrink-0 flex flex-col gap-1 p-2.5 border-r border-gray-200">
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
              className="flex items-center justify-between px-3 py-2 rounded text-sm text-gray-300 cursor-not-allowed select-none"
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
                ? "bg-gray-100 text-gray-900 font-semibold"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-50",
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
