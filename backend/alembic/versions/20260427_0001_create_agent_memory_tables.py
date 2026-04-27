"""create agent memory tables

Revision ID: 20260427_0001
Revises:
Create Date: 2026-04-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260427_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'session_status') THEN
                CREATE TYPE session_status AS ENUM ('running', 'paused', 'completed', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tool_execution_status') THEN
                CREATE TYPE tool_execution_status AS ENUM ('started', 'completed', 'failed');
            END IF;
        END
        $$;
        """
    )

    session_status = sa.Enum(
        "running",
        "paused",
        "completed",
        "failed",
        name="session_status",
        create_type=False,
    )
    tool_execution_status = sa.Enum(
        "started",
        "completed",
        "failed",
        name="tool_execution_status",
        create_type=False,
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("status", session_status, nullable=False, server_default="running"),
        sa.Column("active_agent", sa.String(length=64), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "serialized_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "agent_turns",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("output_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_agent", sa.String(length=64), nullable=True),
        sa.Column(
            "state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "session_id", "turn_index", name="uq_agent_turn_session_turn_index"
        ),
    )
    op.create_index(
        "ix_agent_turns_session_id", "agent_turns", ["session_id"], unique=False
    )

    op.create_table(
        "tool_executions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", tool_execution_status, nullable=False, server_default="started"
        ),
        sa.Column(
            "input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_turn_id"], ["agent_turns.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "session_id", "run_id", name="uq_tool_execution_session_run_id"
        ),
    )
    op.create_index(
        "ix_tool_executions_session_id", "tool_executions", ["session_id"], unique=False
    )
    op.create_index(
        "ix_tool_executions_agent_turn_id",
        "tool_executions",
        ["agent_turn_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tool_executions_agent_turn_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_session_id", table_name="tool_executions")
    op.drop_table("tool_executions")

    op.drop_index("ix_agent_turns_session_id", table_name="agent_turns")
    op.drop_table("agent_turns")

    op.drop_table("sessions")

    op.execute("DROP TYPE IF EXISTS tool_execution_status;")
    op.execute("DROP TYPE IF EXISTS session_status;")
