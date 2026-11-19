"""create jobs, jd_extractions, agent_runs, run_quota, user_answers, events, image_uploads

Idempotent: each object is created only if it does not exist yet, so the migration
can be re-run against a database that was partially or manually set up.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "status IN ('queued','running','awaiting_input')"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _index(name: str, table: str, cols: list[str], **kw) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, cols, **kw)


def upgrade() -> None:
    t = _tables()
    if "jobs" not in t:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source", sa.String(8), nullable=False),
            sa.Column("url", sa.String(2048)),
            sa.Column("raw_text", sa.Text()),
            sa.Column("image_id", sa.String(32)),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("status_reason", sa.String(512)),
            sa.Column("company", sa.String(255)),
            sa.Column("title", sa.String(255)),
            sa.Column("score", sa.Integer()),
            sa.Column("score_breakdown", sa.JSON()),
            sa.Column("musts", sa.JSON(), nullable=False),
            sa.Column("red_flags", sa.JSON(), nullable=False),
            sa.Column("max_pages_override", sa.Integer()),
            sa.Column("content_hash", sa.String(64)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_jobs_user_id", "jobs", ["user_id"])
    _index("ix_jobs_user_status_created", "jobs", ["user_id", "status", "created_at"])
    _index("ix_jobs_user_url", "jobs", ["user_id", "url"])
    _index("ix_jobs_user_content_hash", "jobs", ["user_id", "content_hash"])

    if "jd_extractions" not in t:
        op.create_table(
            "jd_extractions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "job_id",
                sa.String(32),
                sa.ForeignKey("jobs.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("jd", sa.JSON(), nullable=False),
            sa.Column("extractor_version", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_jd_extractions_user_id", "jd_extractions", ["user_id"])

    if "agent_runs" not in t:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column(
                "job_id",
                sa.String(32),
                sa.ForeignKey("jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("profile_version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    _index("ix_agent_runs_job_id", "agent_runs", ["job_id"])
    _index(
        "uq_agent_runs_active_job",
        "agent_runs",
        ["job_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE),
        postgresql_where=sa.text(ACTIVE),
    )

    if "run_quota" not in t:
        op.create_table(
            "run_quota",
            sa.Column("user_id", sa.Uuid(), primary_key=True),
            sa.Column("day", sa.String(10), primary_key=True),
            sa.Column("used", sa.Integer(), nullable=False),
        )

    if "user_answers" not in t:
        op.create_table(
            "user_answers",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("skill", sa.String(255), nullable=False),
            sa.Column("answer", sa.String(8), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "skill"),
        )
    _index("ix_user_answers_user_id", "user_answers", ["user_id"])

    if "events" not in t:
        op.create_table(
            "events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_events_user_id", "events", ["user_id"])

    if "image_uploads" not in t:
        op.create_table(
            "image_uploads",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
            sa.Column("media_type", sa.String(32), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_image_uploads_user_id", "image_uploads", ["user_id"])

    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("profiles")}
    if "indexing_state" not in cols:
        with op.batch_alter_table("profiles") as batch:
            batch.add_column(
                sa.Column(
                    "indexing_state",
                    sa.String(16),
                    nullable=False,
                    server_default="done",
                )
            )


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("profiles")}
    if "indexing_state" in cols:
        with op.batch_alter_table("profiles") as batch:
            batch.drop_column("indexing_state")
    for table in (
        "image_uploads",
        "events",
        "user_answers",
        "run_quota",
        "agent_runs",
        "jd_extractions",
        "jobs",
    ):
        if table in _tables():
            op.drop_table(table)
