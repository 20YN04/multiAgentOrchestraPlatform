from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from multi_agent.state import ExecutionState

from .models import (
    AgentTurnRecord,
    SessionRecord,
    SessionStatus,
    ToolExecutionRecord,
    ToolExecutionStatus,
)
from .serialization import deserialize_state, serialize_state
from .session import session_scope


@dataclass(frozen=True, slots=True)
class SessionBootstrap:
    session_id: uuid.UUID
    state: ExecutionState
    next_turn_index: int
    resumed: bool


class PersistenceError(RuntimeError):
    """Base persistence-layer exception."""


class SessionNotFoundError(PersistenceError):
    """Raised when a requested session does not exist."""


class SessionStateError(PersistenceError):
    """Raised when a session exists but cannot be resumed safely."""


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def _get_session_for_update(db: Session, session_id: uuid.UUID) -> SessionRecord | None:
    stmt = (
        select(SessionRecord)
        .where(SessionRecord.id == session_id)
        .with_for_update(nowait=False)
    )
    return db.execute(stmt).scalar_one_or_none()


class ConversationPersistence:
    """Persistence adapter for LangGraph session checkpoints."""

    def bootstrap_session(
        self,
        *,
        model_name: str,
        prompt: str | None,
        initial_state: ExecutionState,
        resume: bool,
        requested_session_id: str | None,
    ) -> SessionBootstrap:
        if resume:
            if not requested_session_id:
                raise SessionStateError("resume=true requires a session_id.")

            session_id = _as_uuid(requested_session_id)
            with session_scope() as db:
                record = _get_session_for_update(db, session_id)
                if record is None:
                    raise SessionNotFoundError(f"Session {session_id} was not found.")
                if record.status == SessionStatus.COMPLETED:
                    raise SessionStateError(
                        f"Session {session_id} is already completed and cannot be resumed."
                    )
                if record.serialized_state is None:
                    raise SessionStateError(
                        f"Session {session_id} has no checkpointed state to resume from."
                    )

                record.status = SessionStatus.RUNNING
                record.last_error = None

                return SessionBootstrap(
                    session_id=record.id,
                    state=deserialize_state(record.serialized_state),
                    next_turn_index=record.turn_count + 1,
                    resumed=True,
                )

        session_id = (
            _as_uuid(requested_session_id) if requested_session_id else uuid.uuid4()
        )

        with session_scope() as db:
            existing = db.get(SessionRecord, session_id)
            if existing is not None:
                raise SessionStateError(
                    f"Session {session_id} already exists. Use resume=true to continue it."
                )

            db.add(
                SessionRecord(
                    id=session_id,
                    prompt=prompt,
                    model_name=model_name,
                    status=SessionStatus.RUNNING,
                    active_agent=initial_state["active_agent"],
                    turn_count=0,
                    serialized_state=serialize_state(initial_state),
                )
            )

        return SessionBootstrap(
            session_id=session_id,
            state=initial_state,
            next_turn_index=1,
            resumed=False,
        )

    def save_turn_checkpoint(
        self,
        *,
        session_id: str,
        turn_index: int,
        agent_name: str,
        output_content: str,
        next_agent: str | None,
        state: ExecutionState,
    ) -> uuid.UUID:
        session_uuid = _as_uuid(session_id)
        state_payload = serialize_state(state)

        with session_scope() as db:
            record = _get_session_for_update(db, session_uuid)
            if record is None:
                raise SessionNotFoundError(f"Session {session_uuid} was not found.")

            turn_stmt = select(AgentTurnRecord).where(
                AgentTurnRecord.session_id == session_uuid,
                AgentTurnRecord.turn_index == turn_index,
            )
            turn = db.execute(turn_stmt).scalar_one_or_none()

            if turn is None:
                turn = AgentTurnRecord(
                    session_id=session_uuid,
                    turn_index=turn_index,
                    agent_name=agent_name,
                    output_content=output_content,
                    next_agent=next_agent,
                    state_snapshot=state_payload,
                )
                db.add(turn)
                db.flush()
            else:
                turn.agent_name = agent_name
                turn.output_content = output_content
                turn.next_agent = next_agent
                turn.state_snapshot = state_payload

            record.turn_count = max(record.turn_count, turn_index)
            record.active_agent = next_agent
            record.serialized_state = state_payload
            record.status = SessionStatus.RUNNING
            record.last_error = None
            record.updated_at = datetime.now(timezone.utc)

            attach_stmt = select(ToolExecutionRecord).where(
                ToolExecutionRecord.session_id == session_uuid,
                ToolExecutionRecord.turn_index == turn_index,
                ToolExecutionRecord.agent_turn_id.is_(None),
            )
            tool_records = list(db.execute(attach_stmt).scalars().all())
            for tool_record in tool_records:
                tool_record.agent_turn_id = turn.id

            return turn.id

    def mark_session_completed(
        self, *, session_id: str, final_state: ExecutionState
    ) -> None:
        session_uuid = _as_uuid(session_id)
        with session_scope() as db:
            record = _get_session_for_update(db, session_uuid)
            if record is None:
                raise SessionNotFoundError(f"Session {session_uuid} was not found.")

            record.status = SessionStatus.COMPLETED
            record.serialized_state = serialize_state(final_state)
            record.updated_at = datetime.now(timezone.utc)
            record.last_error = None

    def mark_session_paused(
        self, *, session_id: str, reason: str | None = None
    ) -> None:
        session_uuid = _as_uuid(session_id)
        with session_scope() as db:
            record = _get_session_for_update(db, session_uuid)
            if record is None:
                return

            record.status = SessionStatus.PAUSED
            record.last_error = reason
            record.updated_at = datetime.now(timezone.utc)

    def mark_session_failed(self, *, session_id: str, error_message: str) -> None:
        session_uuid = _as_uuid(session_id)
        with session_scope() as db:
            record = _get_session_for_update(db, session_uuid)
            if record is None:
                return

            record.status = SessionStatus.FAILED
            record.last_error = error_message
            record.updated_at = datetime.now(timezone.utc)

    def record_tool_start(
        self,
        *,
        session_id: str,
        run_id: str,
        turn_index: int,
        agent_name: str,
        tool_name: str,
        input_payload: dict[str, Any] | None,
    ) -> None:
        session_uuid = _as_uuid(session_id)
        with session_scope() as db:
            stmt = select(ToolExecutionRecord).where(
                ToolExecutionRecord.session_id == session_uuid,
                ToolExecutionRecord.run_id == run_id,
            )
            record = db.execute(stmt).scalar_one_or_none()

            if record is None:
                db.add(
                    ToolExecutionRecord(
                        session_id=session_uuid,
                        run_id=run_id,
                        turn_index=turn_index,
                        agent_name=agent_name,
                        tool_name=tool_name,
                        status=ToolExecutionStatus.STARTED,
                        input_payload=input_payload,
                    )
                )
                return

            record.turn_index = turn_index
            record.agent_name = agent_name
            record.tool_name = tool_name
            record.status = ToolExecutionStatus.STARTED
            record.input_payload = input_payload
            record.output_payload = None
            record.error_message = None
            record.completed_at = None

    def record_tool_end(
        self,
        *,
        session_id: str,
        run_id: str,
        output_payload: dict[str, Any] | None,
        error_message: str | None,
    ) -> None:
        session_uuid = _as_uuid(session_id)
        with session_scope() as db:
            stmt = select(ToolExecutionRecord).where(
                ToolExecutionRecord.session_id == session_uuid,
                ToolExecutionRecord.run_id == run_id,
            )
            record = db.execute(stmt).scalar_one_or_none()

            if record is None:
                return

            record.output_payload = output_payload
            record.error_message = error_message
            record.completed_at = datetime.now(timezone.utc)
            record.status = (
                ToolExecutionStatus.FAILED
                if error_message is not None
                else ToolExecutionStatus.COMPLETED
            )
