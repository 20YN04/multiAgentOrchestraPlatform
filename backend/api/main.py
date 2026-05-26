from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

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

# CORS — env-driven; no wildcard in production.
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-API-Key"],
)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_API_KEY = os.getenv("API_KEY", "")


def _check_api_key(request: Request) -> bool:
    """Return True when the request carries a valid API key."""
    if not _API_KEY:
        # Key not configured — block all requests rather than allow them through.
        return False
    return request.headers.get("X-API-Key") == _API_KEY


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
    if not _check_api_key(http_request):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

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
