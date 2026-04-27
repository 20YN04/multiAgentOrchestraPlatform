import { AgentStreamTerminal } from "../../components/agents/AgentStreamTerminal";

export default function AgentConsolePage(): JSX.Element {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_20%_15%,#1f2937_0%,#0b0f17_35%,#020617_100%)]">
      <AgentStreamTerminal />
    </main>
  );
}