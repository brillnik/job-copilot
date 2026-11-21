"""training consent log and extractor shadow runs

Adds training_consent_log (append-only) and extractor_shadow_runs (shared system
table, no user_id). Idempotent: every object is created only if missing.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if "training_consent_log" not in _tables():
        op.create_table(
            "training_consent_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("policy_version", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_training_consent_user_id_id" not in _indexes("training_consent_log"):
        op.create_index(
            "ix_training_consent_user_id_id", "training_consent_log", ["user_id", "id"]
        )

    if "extractor_shadow_runs" not in _tables():
        op.create_table(
            "extractor_shadow_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(8), nullable=False),
            sa.Column("slice", sa.String(64), nullable=False),
            sa.Column("results", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_shadow_kind_slice" not in _indexes("extractor_shadow_runs"):
        op.create_index(
            "ix_shadow_kind_slice", "extractor_shadow_runs", ["kind", "slice"]
        )


def downgrade() -> None:
    for table in ("extractor_shadow_runs", "training_consent_log"):
        if table in _tables():
            op.drop_table(table)
