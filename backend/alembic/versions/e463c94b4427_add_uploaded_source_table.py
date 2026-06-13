"""add uploaded source table

Revision ID: e463c94b4427
Revises: b031b074ae3f
Create Date: 2026-06-13 23:33:49.222203

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "e463c94b4427"
down_revision: str | None = "b031b074ae3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploadedsource",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("raw_data_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("uploadedsource")
