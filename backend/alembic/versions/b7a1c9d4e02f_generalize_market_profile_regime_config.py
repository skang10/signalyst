"""generalize market profile regime config

Revision ID: b7a1c9d4e02f
Revises: e463c94b4427
Create Date: 2026-06-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "b7a1c9d4e02f"
down_revision: str | None = "e463c94b4427"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketprofile",
        sa.Column("default_connector_params", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "marketprofile",
        sa.Column("regime_thresholds", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "marketprofile",
        sa.Column(
            "primary_ticker", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("marketprofile", "primary_ticker")
    op.drop_column("marketprofile", "regime_thresholds")
    op.drop_column("marketprofile", "default_connector_params")
