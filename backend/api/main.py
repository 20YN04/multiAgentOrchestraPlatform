from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import StreamingResponse

from init_db import initialize_database

from .models import AgentRunRequest
from .service import stream_agent_run

app = FastAPI(title="Multi-Agent Orchestration API", version="1.0.0")

AUTO_MIGRATE_ON_STARTUP = os.getenv("AUTO_MIGRATE_ON_STARTUP", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@app.on_event("startup")
def run_database_migrations() -> None:
    if AUTO_MIGRATE_ON_STARTUP:
        initialize_database()


@router.post("/run", response_class=StreamingResponse)
async def run_agents(
    request: AgentRunRequest,
    http_request: Request,
) -> StreamingResponse:
    """
    Start the LangGraph multi-agent workflow and stream SSE JSON events.
    """
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_agent_run(request, client_request=http_request),
        media_type="text/event-stream",
        headers=headers,
    )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
