"""v1_initial_schema

Revision ID: 83540d9bcbbc
Revises:
Create Date: 2026-05-11 22:55:56.946698

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "83540d9bcbbc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("world_setting", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "event_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("data", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_log_entity_id"), "event_log", ["entity_id"], unique=False)
    op.create_index(op.f("ix_event_log_event_type"), "event_log", ["event_type"], unique=False)
    op.create_table(
        "characters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("player_name", sa.String(length=100), nullable=True),
        sa.Column("character_name", sa.String(length=100), nullable=False),
        sa.Column("race", sa.String(length=50), nullable=True),
        sa.Column("class", sa.String(length=50), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("experience", sa.Integer(), nullable=True),
        sa.Column("hp_current", sa.Integer(), nullable=True),
        sa.Column("hp_max", sa.Integer(), nullable=True),
        sa.Column("strength", sa.Integer(), nullable=True),
        sa.Column("dexterity", sa.Integer(), nullable=True),
        sa.Column("constitution", sa.Integer(), nullable=True),
        sa.Column("intelligence", sa.Integer(), nullable=True),
        sa.Column("wisdom", sa.Integer(), nullable=True),
        sa.Column("charisma", sa.Integer(), nullable=True),
        sa.Column("armor_class", sa.Integer(), nullable=True),
        sa.Column("initiative", sa.Integer(), nullable=True),
        sa.Column("speed", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.Column("ended_at", sa.String(length=32), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "world_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "abilities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uses_remaining", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conditions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("condition_name", sa.String(length=100), nullable=False),
        sa.Column("duration", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inventory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("item_type", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("fact_type", sa.String(length=50), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=True),
        sa.Column("extracted_by", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=True),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=True),
        sa.Column("action_text", sa.Text(), nullable=True),
        sa.Column("dice_results", sa.Text(), nullable=True),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("scene_id", sa.String(length=36), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("summaries")
    op.drop_table("turns")
    op.drop_table("scenes")
    op.drop_table("memories")
    op.drop_table("inventory")
    op.drop_table("conditions")
    op.drop_table("abilities")
    op.drop_table("world_state")
    op.drop_table("sessions")
    op.drop_table("characters")
    op.drop_index(op.f("ix_event_log_event_type"), table_name="event_log")
    op.drop_index(op.f("ix_event_log_entity_id"), table_name="event_log")
    op.drop_table("event_log")
    op.drop_table("campaigns")
