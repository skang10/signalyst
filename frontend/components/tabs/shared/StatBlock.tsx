type Props = {
  value: string | number;
  label: string;
  accentClassName?: string;
};

export function StatBlock({ value, label, accentClassName }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <div className={`text-lg font-mono font-bold ${accentClassName ?? "text-gray-700"}`}>
        {value}
      </div>
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">{label}</div>
    </div>
  );
}
