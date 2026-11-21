"""tailoring examples (approvals.jd_embedding) and the screening-answer bank

Adds approvals.{jd_embedding,jd_embedding_model} and the screening_answers table.

Idempotent: every object is created only if missing.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    cols = {c["name"] for c in _insp().get_columns("approvals")}
    if "jd_embedding" not in cols:
        op.add_column("approvals", sa.Column("jd_embedding", sa.JSON()))
    if "jd_embedding_model" not in cols:
        op.add_column("approvals", sa.Column("jd_embedding_model", sa.String(128)))

    if "screening_answers" not in _insp().get_table_names():
        op.create_table(
            "screening_answers",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("normalised_question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("field_type", sa.String(32), nullable=False),
            sa.Column("embedding", sa.JSON(), nullable=False),
            sa.Column("embedding_model", sa.String(128)),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    have = {i["name"] for i in _insp().get_indexes("screening_answers")}
    if "ix_screening_answers_user_id" not in have:
        op.create_index(
            "ix_screening_answers_user_id", "screening_answers", ["user_id"]
        )
    if "ix_screening_user_type" not in have:
        op.create_index(
            "ix_screening_user_type", "screening_answers", ["user_id", "field_type"]
        )


def downgrade() -> None:
    op.drop_table("screening_answers")
    with op.batch_alter_table("approvals") as batch:
        batch.drop_column("jd_embedding_model")
        batch.drop_column("jd_embedding")
