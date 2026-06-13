"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_PATHS = new Set(["overview", "features", "backtest"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 pt-3 pb-1 text-[10px] font-semibold tracking-widest text-gray-400 uppercase select-none">
      {children}
    </div>
  );
}

function NavItem({
  label,
  path,
  badge,
  sessionId,
  pathname,
  stage,
}: {
  label: string;
  path: string;
  badge?: string;
  sessionId: string;
  pathname: string;
  stage: string | null;
}) {
  const href = `/sessions/${sessionId}/${path}`;
  const isActive = pathname === href;

  const isLocked =
    (path === "data" && stage !== null && DATA_LOCKED_STAGES.has(stage)) ||
    (RESULTS_PATHS.has(path) && stage !== RESULTS_UNLOCKED_STAGE);

  if (isLocked) {
    return (
      <span
        title="Locked — not available at this stage"
        className="flex items-center justify-between px-3 py-2 rounded text-sm text-gray-300 cursor-not-allowed select-none"
      >
        {label}
        <span aria-hidden>🔒</span>
      </span>
    );
  }

  return (
    <Link
      href={href}
      className={[
        "px-3 py-2 rounded text-sm transition-colors",
        isActive
          ? "bg-gray-100 text-gray-900 font-semibold"
          : "text-gray-600 hover:text-gray-900 hover:bg-gray-50",
      ].join(" ")}
    >
      {label}
      {badge}
    </Link>
  );
}

export function SessionSidebar({
  sessionId,
  stage,
}: {
  sessionId: string;
  stage: string | null;
}) {
  const pathname = usePathname();

  return (
    <nav className="w-[170px] flex-shrink-0 flex flex-col p-2.5 border-r border-gray-200">
      <SectionLabel>Navigation</SectionLabel>
      <NavItem
        label="Agent Chat"
        path="activity"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />

      <SectionLabel>Data</SectionLabel>
      <NavItem
        label="Config"
        path="config"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />
      <NavItem
        label="Data Status"
        path="data"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />

      <SectionLabel>Results</SectionLabel>
      <NavItem
        label="Overview"
        path="overview"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />
      <NavItem
        label="Features"
        path="features"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />
      <NavItem
        label="Backtest"
        path="backtest"
        sessionId={sessionId}
        pathname={pathname}
        stage={stage}
      />
    </nav>
  );
}
