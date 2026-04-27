"use client";

import { FormEvent, useMemo, useState } from "react";

import type { AgentEventType, AgentTurnEvent } from "../../lib/agent-stream-types";
import { useAgentStream } from "../../hooks/useAgentStream";

const AGENT_LABELS: Record<string, string> = {
  researcher: "Researcher",
  coder: "Coder",
  qa_tester: "QA Tester",
  system: "System",
};

function prettifyAgentName(agentName: string): string {
  return AGENT_LABELS[agentName] ?? agentName;
}

function eventLabel(type: AgentEventType): string {
  if (type === "thought") {
    return "Thought";
  }
  if (type === "tool_execution") {
    return "Tool Usage";
  }
  if (type === "final_answer") {
    return "Code Output";
  }
  return "Error";
}

function eventStyles(type: AgentEventType): string {
  if (type === "thought") {
    return "border-sky-400/50 bg-sky-500/10 text-sky-100";
  }
  if (type === "tool_execution") {
    return "border-amber-400/50 bg-amber-500/10 text-amber-100";
  }
  if (type === "final_answer") {
    return "border-emerald-400/50 bg-emerald-500/10 text-emerald-100";
  }
  return "border-rose-400/60 bg-rose-500/10 text-rose-100";
}

function EventRow({ event }: { event: AgentTurnEvent }): JSX.Element {
  return (
    <div className={`rounded-md border px-3 py-2 ${eventStyles(event.event_type)}`}>
      <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-[0.14em] opacity-90">
        <span>{eventLabel(event.event_type)}</span>
        <span>{new Date(event.receivedAt).toLocaleTimeString()}</span>
      </div>
      <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-6">
        {event.content}
      </pre>
    </div>
  );
}

export function AgentStreamTerminal(): JSX.Element {
  const [prompt, setPrompt] = useState(
    "Research a scalable architecture and then produce an implementation blueprint."
  );
  const { status, turns, errorMessage, startStream, stopStream, reset } = useAgentStream();

  const statusTone = useMemo(() => {
    if (status === "error") {
      return "text-rose-300";
    }
    if (status === "streaming" || status === "connecting") {
      return "text-amber-300";
    }
    if (status === "completed") {
      return "text-emerald-300";
    }
    return "text-zinc-300";
  }, [status]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    startStream({ prompt, modelName: "gpt-4o-mini", temperature: 0.1, timeoutSeconds: 120 });
  };

  return (
    <section className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-[0_0_80px_-20px_rgba(20,184,166,0.35)]">
        <div className="border-b border-zinc-800 bg-zinc-900/70 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="font-mono text-lg tracking-wide text-zinc-100">Agent Console</h1>
            <span className={`font-mono text-xs uppercase tracking-[0.15em] ${statusTone}`}>
              {status}
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="border-b border-zinc-800 p-4 sm:p-6">
          <label htmlFor="agent-prompt" className="mb-2 block font-mono text-xs uppercase tracking-[0.14em] text-zinc-400">
            Prompt
          </label>
          <textarea
            id="agent-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={4}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-500/30"
            placeholder="Describe what the multi-agent system should do..."
          />

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="submit"
              className="rounded-md border border-teal-300/50 bg-teal-300/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.14em] text-teal-100 transition hover:bg-teal-300/20"
            >
              Run Workflow
            </button>
            <button
              type="button"
              onClick={stopStream}
              className="rounded-md border border-amber-300/50 bg-amber-300/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.14em] text-amber-100 transition hover:bg-amber-300/20"
            >
              Stop
            </button>
            <button
              type="button"
              onClick={reset}
              className="rounded-md border border-zinc-500/60 bg-zinc-800 px-4 py-2 font-mono text-xs uppercase tracking-[0.14em] text-zinc-200 transition hover:bg-zinc-700"
            >
              Clear
            </button>
          </div>

          {errorMessage ? (
            <p className="mt-3 font-mono text-xs text-rose-300">{errorMessage}</p>
          ) : null}
        </form>

        <div className="max-h-[60vh] space-y-6 overflow-y-auto p-4 sm:p-6">
          {turns.length === 0 ? (
            <div className="rounded-lg border border-dashed border-zinc-700 px-4 py-6 text-center font-mono text-sm text-zinc-500">
              Waiting for stream events...
            </div>
          ) : null}

          {turns.map((turn, turnIndex) => (
            <article key={turn.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
              <header className="mb-3 flex items-center justify-between gap-2">
                <h2 className="font-mono text-sm uppercase tracking-[0.14em] text-teal-200">
                  Turn {turnIndex + 1}: {prettifyAgentName(turn.agentName)}
                </h2>
                <span className="font-mono text-[11px] text-zinc-500">
                  {new Date(turn.startedAt).toLocaleTimeString()}
                </span>
              </header>

              <div className="space-y-3">
                {turn.events.map((streamEvent) => (
                  <EventRow key={streamEvent.id} event={streamEvent} />
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}