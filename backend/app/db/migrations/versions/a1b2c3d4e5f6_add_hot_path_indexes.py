"""add hot-path indexes on session/campaign foreign keys

Indexes the foreign-key columns that the per-turn context builder filters on
every turn (session_id / campaign_id). Without them SQLite full-scans these
tables, which grows linearly with session length.

Idempotent: uses ``CREATE INDEX IF NOT EXISTS`` because the app's startup
``create_all`` may already have created the same indexes from the model
metadata on an existing database.

Revision ID: a1b2c3d4e5f6
Revises: 1d43553f48cb
Create Date: 2026-06-05 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "1d43553f48cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_characters_campaign_id", "characters", "campaign_id"),
    ("ix_sessions_campaign_id", "sessions", "campaign_id"),
    ("ix_turns_session_id", "turns", "session_id"),
    ("ix_scenes_session_id", "scenes", "session_id"),
    ("ix_memories_session_id", "memories", "session_id"),
    ("ix_summaries_session_id", "summaries", "session_id"),
)


def upgrade() -> None:
    """Create hot-path indexes if they do not already exist."""
    for name, table, column in _INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")')
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_memories_session_importance" '
        'ON "memories" ("session_id", "importance")'
    )


def downgrade() -> None:
    """Drop the hot-path indexes."""
    op.execute('DROP INDEX IF EXISTS "ix_memories_session_importance"')
    for name, _table, _column in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
