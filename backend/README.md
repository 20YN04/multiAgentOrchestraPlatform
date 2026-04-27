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
- `db/models.py`: SQLAlchemy models for sessions, turns, and tools
- `db/checkpointing.py`: checkpoint persistence and resume service
- `db/serialization.py`: LangGraph state serialization/deserialization
- `init_db.py`: startup-safe migration entrypoint
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
  "timeout_seconds": 120,
  "session_id": null,
  "resume": false
}
```

Resume request body example:

```json
{
  "session_id": "4f1f7844-b94e-47b6-a5c4-7ae73fd65635",
  "resume": true,
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

## Long-term memory (PostgreSQL)

The persistence layer stores:

- `sessions`: current resumable snapshot and lifecycle status
- `agent_turns`: one durable checkpoint per completed node execution
- `tool_executions`: tool start/end telemetry linked to session and turn

Checkpointing behavior:

- At the end of every agent node execution, the full LangGraph state is serialized and written to PostgreSQL.
- `active_agent` is advanced to the next routable node, so resuming starts at the correct next agent.
- If the stream times out or the client disconnects, the session is marked `paused` and can be resumed with `resume=true`.

## Automatic migrations on startup

- `api.main` runs `initialize_database()` at startup when `AUTO_MIGRATE_ON_STARTUP=true`.
- `init_db.py` waits for PostgreSQL readiness and applies Alembic migrations under a PostgreSQL advisory lock.
- This prevents concurrent migration races when multiple containers start together.

Run migrations manually:

```bash
python backend/init_db.py
```

## Docker notes

The included `docker-compose.yml` uses a named volume:

- `postgres_data:/var/lib/postgresql/data`

This ensures local DB state persists across machine restarts.

## Add a QA Tester later

1. Add a `QA_TESTER` prompt/spec in `multi_agent/graph.py`.
2. Include that spec when calling `build_execution_graph`.
3. Extend progression order, for example:
   - `("researcher", "coder", "qa_tester")`
4. Update routing directives in prompts to include `NEXT: QA_TESTER`.

No architectural rewiring is needed because the graph builder and router are already generic.