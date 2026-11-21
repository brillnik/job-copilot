"""applications, apply caps, site state, users.autopilot, agent_runs.autopilot

Idempotent: every object is created only if missing, so it can be re-run against a
database that was partially or manually set up.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_insp().get_table_names())


def _cols(table: str) -> set[str]:
    return {c["name"] for c in _insp().get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in _insp().get_indexes(table)}


def _index(name: str, table: str, cols: list[str], **kw) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, cols, **kw)


def upgrade() -> None:
    t = _tables()
    if "applications" not in t:
        op.create_table(
            "applications",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column(
                "job_id",
                sa.String(32),
                sa.ForeignKey("jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("run_id", sa.String(32), nullable=False),
            sa.Column("channel", sa.String(12), nullable=False),
            sa.Column("mode", sa.String(10), nullable=False),
            sa.Column("ats", sa.String(16)),
            sa.Column("site", sa.String(32), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("skip_reason", sa.String(64)),
            sa.Column("apply_url", sa.String(2048), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True)),
            sa.Column("answers_used", sa.JSON(), nullable=False),
            sa.Column("screenshot_keys", sa.JSON(), nullable=False),
            sa.Column("pending_fields", sa.JSON(), nullable=False),
            sa.Column("provided_answers", sa.JSON(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("slot_held", sa.Boolean(), nullable=False),
            sa.Column("slot_day", sa.String(10)),
            sa.Column("slot_hour", sa.String(13)),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index(
        "uq_applications_user_job", "applications", ["user_id", "job_id"], unique=True
    )
    _index("ix_applications_user_status", "applications", ["user_id", "status"])

    if "apply_quota" not in t:
        op.create_table(
            "apply_quota",
            sa.Column("user_id", sa.Uuid(), primary_key=True),
            sa.Column("day", sa.String(10), primary_key=True),
            sa.Column("site", sa.String(32), primary_key=True),
            sa.Column("used", sa.Integer(), nullable=False),
        )
    if "ats_hourly_quota" not in t:
        op.create_table(
            "ats_hourly_quota",
            sa.Column("ats", sa.String(16), primary_key=True),
            sa.Column("hour", sa.String(13), primary_key=True),
            sa.Column("used", sa.Integer(), nullable=False),
        )
    if "apply_site_state" not in t:
        op.create_table(
            "apply_site_state",
            sa.Column("user_id", sa.Uuid(), primary_key=True),
            sa.Column("site", sa.String(32), primary_key=True),
            sa.Column("consecutive_blocks", sa.Integer(), nullable=False),
            sa.Column("paused_at", sa.DateTime(timezone=True)),
            sa.Column("last_reason", sa.String(64)),
        )

    if "autopilot" not in _cols("users"):
        op.add_column("users", sa.Column("autopilot", sa.JSON()))
    if "autopilot" not in _cols("agent_runs"):
        op.add_column(
            "agent_runs",
            sa.Column(
                "autopilot", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    for table in (
        "apply_site_state",
        "ats_hourly_quota",
        "apply_quota",
        "applications",
    ):
        if table in _tables():
            op.drop_table(table)
    for table, col in (("agent_runs", "autopilot"), ("users", "autopilot")):
        if col in _cols(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(col)
