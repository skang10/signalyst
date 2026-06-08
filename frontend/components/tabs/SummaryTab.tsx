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
      <div className="bg-white border border-gray-200 rounded p-5">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-4">
          Agent Narrative
        </div>
        <p
          className="text-sm text-gray-700 leading-7"
          dangerouslySetInnerHTML={{ __html: renderSummary(summary) }}
        />
      </div>
    </div>
  );
}
