"""gmail reply tracking

Adds gmail_connections and email_events. Idempotent: every object is created only if
missing.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index(name: str, table: str, cols: list[str], **kw) -> None:
    have = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in have:
        op.create_index(name, table, cols, **kw)


def upgrade() -> None:
    t = _tables()
    if "gmail_connections" not in t:
        op.create_table(
            "gmail_connections",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False, unique=True),
            sa.Column("token_ciphertext", sa.Text(), nullable=False),
            sa.Column("email_hash", sa.String(64), nullable=False),
            sa.Column("history_id", sa.String(32)),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        )
    _index("ix_gmail_connections_email_hash", "gmail_connections", ["email_hash"])
    if "email_events" not in t:
        op.create_table(
            "email_events",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("gmail_message_id", sa.String(64), nullable=False),
            sa.Column(
                "job_id",
                sa.String(32),
                sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            ),
            sa.Column("classification", sa.String(16), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("applied_to_tracker", sa.Boolean(), nullable=False),
            sa.Column("suggested_column", sa.String(16)),
            sa.Column("suggestion_status", sa.String(16)),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
        )
    _index(
        "uq_email_user_message",
        "email_events",
        ["user_id", "gmail_message_id"],
        unique=True,
    )
    _index(
        "ix_email_user_suggestion",
        "email_events",
        ["user_id", "suggestion_status"],
    )


def downgrade() -> None:
    for table in ("email_events", "gmail_connections"):
        if table in _tables():
            op.drop_table(table)
