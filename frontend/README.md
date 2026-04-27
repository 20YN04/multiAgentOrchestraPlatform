# Frontend Agent Stream UI (Next.js + React + Tailwind)

This folder contains a ready-to-use streaming UI for the multi-agent backend.

## What is included

- `src/hooks/useAgentStream.ts`
  - Native `EventSource` management
  - Strict JSON parsing for stream events
  - Reducer-based grouping into agent turns
- `src/app/api/agents/run/route.ts`
  - Next.js server route proxy
  - Accepts GET for browser `EventSource`
  - Forwards to FastAPI `POST /api/v1/agents/run`
- `src/components/agents/AgentStreamTerminal.tsx`
  - Terminal-like Tailwind UI
  - Visual styles for Thoughts, Tool Usage, and Code Output
- `src/app/agent-console/page.tsx`
  - Example page rendering the UI

## Environment

Set backend base URL in your Next.js app:

```bash
NEXT_PUBLIC_AGENT_API_BASE_URL=http://127.0.0.1:8000
```

## Event contract expected from backend

Each SSE frame must be:

```json
{
  "agent_name": "researcher",
  "event_type": "thought",
  "content": "..."
}
```

Supported event types:

- `thought`
- `tool_execution`
- `final_answer`
- `error`