"""add_session_events (M11 per-session engine event store)

Revision ID: b2e7c1a9d4f0
Revises: 1d43553f48cb
Create Date: 2026-06-07 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2e7c1a9d4f0'
down_revision: str | Sequence[str] | None = '1d43553f48cb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the session_events table — the engine's per-session save file."""
    op.create_table(
        "session_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_events_session_seq",
        "session_events",
        ["session_id", "seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_session_events_session_seq", table_name="session_events")
    op.drop_table("session_events")
