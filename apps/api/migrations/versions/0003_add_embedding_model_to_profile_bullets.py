"""add embedding_model to profile_bullets

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rows indexed before this column existed all used the hashing embedder.
    with op.batch_alter_table("profile_bullets") as batch:
        batch.add_column(
            sa.Column(
                "embedding_model",
                sa.String(length=128),
                nullable=False,
                server_default="hashing-512",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("profile_bullets") as batch:
        batch.drop_column("embedding_model")
