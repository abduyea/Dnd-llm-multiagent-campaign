"""add_attack_result_to_turns

Revision ID: 1d43553f48cb
Revises: 83540d9bcbbc
Create Date: 2026-05-14 01:11:08.771750

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '1d43553f48cb'
down_revision: str | Sequence[str] | None = '83540d9bcbbc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add attack_result JSON column to turns table."""
    op.add_column("turns", sa.Column("attack_result", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove attack_result column from turns table."""
    op.drop_column("turns", "attack_result")
