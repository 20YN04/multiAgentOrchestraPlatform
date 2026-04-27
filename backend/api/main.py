from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse

from .models import AgentRunRequest
from .service import stream_agent_run

app = FastAPI(title="Multi-Agent Orchestration API", version="1.0.0")

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/run", response_class=StreamingResponse)
async def run_agents(request: AgentRunRequest) -> StreamingResponse:
    """
    Start the LangGraph multi-agent workflow and stream SSE JSON events.
    """
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_agent_run(request),
        media_type="text/event-stream",
        headers=headers,
    )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)