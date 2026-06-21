import type { LucideIcon } from "lucide-react";

type Props = {
  icon: LucideIcon;
  title: string;
  className?: string;
  children: React.ReactNode;
};

export function DashboardCard({ icon: Icon, title, className, children }: Props) {
  return (
    <div className={`bg-white border border-gray-200 rounded p-4 flex flex-col gap-2 ${className ?? ""}`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3 h-3 text-gray-400" strokeWidth={2} />
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
          {title}
        </div>
      </div>
      {children}
    </div>
  );
}
