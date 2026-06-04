"""add cascade delete to session artifact fks

Revision ID: b031b074ae3f
Revises: 7cf099bea84b
Create Date: 2026-06-04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b031b074ae3f"
down_revision: str | None = "7cf099bea84b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # dataartifact.session_id → session.id
    op.drop_constraint("dataartifact_session_id_fkey", "dataartifact", type_="foreignkey")
    op.create_foreign_key(
        "dataartifact_session_id_fkey",
        "dataartifact",
        "session",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # featureartifact.session_id → session.id
    op.drop_constraint("featureartifact_session_id_fkey", "featureartifact", type_="foreignkey")
    op.create_foreign_key(
        "featureartifact_session_id_fkey",
        "featureartifact",
        "session",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # featureartifact.data_artifact_id → dataartifact.id
    op.drop_constraint(
        "featureartifact_data_artifact_id_fkey", "featureartifact", type_="foreignkey"
    )
    op.create_foreign_key(
        "featureartifact_data_artifact_id_fkey",
        "featureartifact",
        "dataartifact",
        ["data_artifact_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # analysisresult.session_id → session.id
    op.drop_constraint("analysisresult_session_id_fkey", "analysisresult", type_="foreignkey")
    op.create_foreign_key(
        "analysisresult_session_id_fkey",
        "analysisresult",
        "session",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # analysisresult.feature_artifact_id → featureartifact.id
    op.drop_constraint(
        "analysisresult_feature_artifact_id_fkey", "analysisresult", type_="foreignkey"
    )
    op.create_foreign_key(
        "analysisresult_feature_artifact_id_fkey",
        "analysisresult",
        "featureartifact",
        ["feature_artifact_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "analysisresult_feature_artifact_id_fkey", "analysisresult", type_="foreignkey"
    )
    op.create_foreign_key(
        "analysisresult_feature_artifact_id_fkey",
        "analysisresult",
        "featureartifact",
        ["feature_artifact_id"],
        ["id"],
    )

    op.drop_constraint("analysisresult_session_id_fkey", "analysisresult", type_="foreignkey")
    op.create_foreign_key(
        "analysisresult_session_id_fkey",
        "analysisresult",
        "session",
        ["session_id"],
        ["id"],
    )

    op.drop_constraint(
        "featureartifact_data_artifact_id_fkey", "featureartifact", type_="foreignkey"
    )
    op.create_foreign_key(
        "featureartifact_data_artifact_id_fkey",
        "featureartifact",
        "dataartifact",
        ["data_artifact_id"],
        ["id"],
    )

    op.drop_constraint("featureartifact_session_id_fkey", "featureartifact", type_="foreignkey")
    op.create_foreign_key(
        "featureartifact_session_id_fkey",
        "featureartifact",
        "session",
        ["session_id"],
        ["id"],
    )

    op.drop_constraint("dataartifact_session_id_fkey", "dataartifact", type_="foreignkey")
    op.create_foreign_key(
        "dataartifact_session_id_fkey",
        "dataartifact",
        "session",
        ["session_id"],
        ["id"],
    )
