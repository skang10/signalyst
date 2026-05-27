"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-05-04

"""

from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Any = None
branch_labels: Any = None
depends_on: Any = None


def upgrade() -> None:
    op.create_table(
        "run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("date_range_start", sa.String(), nullable=False),
        sa.Column("date_range_end", sa.String(), nullable=False),
        sa.Column("tasks", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("run")
