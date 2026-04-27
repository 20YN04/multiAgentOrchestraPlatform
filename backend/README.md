# Multi-Agent Execution Graph (LangGraph)

## What is included

- Typed shared state with:
  - full message history (`messages`)
  - current active agent (`active_agent`)
- Two LLM-powered nodes:
  - `researcher`
  - `coder`
- Router that inspects the latest output directive:
  - `NEXT: RESEARCHER`
  - `NEXT: CODER`
  - `NEXT: FINISHED`
- Generic graph builder so you can add new agents without rewriting core orchestration.

## File layout

- `multi_agent/state.py`: typed state and route contracts
- `multi_agent/llm.py`: foundational model factory
- `multi_agent/nodes.py`: agent node factory
- `multi_agent/routing.py`: routing logic
- `multi_agent/graph.py`: StateGraph assembly
- `run_example.py`: minimal runnable entrypoint

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Set your LLM credentials (for OpenAI-backed `ChatOpenAI`) and run:

```bash
python backend/run_example.py
```

## Run API (SSE)

Start FastAPI:

```bash
uvicorn api.main:app --app-dir backend --reload
```

Endpoint:

- `POST /api/v1/agents/run`

Request body:

```json
{
  "prompt": "Design a resilient event-driven architecture for order processing.",
  "model_name": "gpt-4o-mini",
  "temperature": 0.1,
  "timeout_seconds": 120
}
```

SSE payload format (strict JSON):

```json
{
  "agent_name": "researcher",
  "event_type": "thought",
  "content": "..."
}
```

`event_type` values:

- `thought`
- `tool_execution`
- `final_answer`
- `error`

## Add a QA Tester later

1. Add a `QA_TESTER` prompt/spec in `multi_agent/graph.py`.
2. Include that spec when calling `build_execution_graph`.
3. Extend progression order, for example:
   - `("researcher", "coder", "qa_tester")`
4. Update routing directives in prompts to include `NEXT: QA_TESTER`.

No architectural rewiring is needed because the graph builder and router are already generic.