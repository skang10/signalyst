import { TopBar } from "@/components/TopBar";
import { AgentStream } from "@/components/AgentStream";
import { ResultsPanel } from "@/components/ResultsPanel";
import { ChatPanel } from "@/components/ChatPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-[#0f0f1a]">
      <TopBar />
      <AgentStream />
      <main className="flex flex-1 overflow-hidden">
        <section className="flex-1 overflow-hidden">
          <ResultsPanel />
        </section>
        <ChatPanel />
      </main>
    </div>
  );
}
