import { TabPlaceholder } from "./TabPlaceholder";

type Props = { summary: string };

function renderSummary(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function SummaryTab({ summary }: Props) {
  if (!summary) {
    return (
      <TabPlaceholder
        icon="✎"
        title="No summary available"
        reason="The agent did not produce a written summary for this run."
      />
    );
  }

  return (
    <div className="p-4 h-full overflow-y-auto">
      <div className="bg-[#0d0d18] border border-slate-800 rounded p-5">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-4">
          Agent Narrative
        </div>
        <p
          className="text-sm text-slate-300 leading-7"
          dangerouslySetInnerHTML={{ __html: renderSummary(summary) }}
        />
      </div>
    </div>
  );
}
