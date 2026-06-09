type TabPlaceholderProps = {
  icon: string;
  title: string;
  reason: string;
};

export function TabPlaceholder({ icon, title, reason }: TabPlaceholderProps) {
  return (
    <div className="flex items-center justify-center h-full min-h-[180px]">
      <div className="text-center max-w-[280px]">
        <div className="text-[28px] text-gray-200 mb-3">{icon}</div>
        <div className="text-xs text-gray-500 font-mono font-semibold mb-1.5">
          {title}
        </div>
        <div className="text-[10px] text-gray-400 font-mono leading-relaxed">
          {reason}
        </div>
      </div>
    </div>
  );
}
