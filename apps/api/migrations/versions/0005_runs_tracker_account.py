"""runs (review/approval), tracker, settings and account

Extends agent_runs; adds run_events, drafts, approvals, tracker_cards, consent_log,
exports, deletion_audit; adds users.{status,sessions_valid_after,preferences,
preferences_rev} and user_answers.detail. Renames run status awaiting_input to
waiting_for_user (data and the active-run partial index).

Idempotent: every object is created only if missing, so it can be re-run against a
database that was partially or manually set up.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "status IN ('queued','running','waiting_for_user')"


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


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _cols(table):
        op.add_column(table, column)


def _uuid_user(fk: bool = False) -> sa.Column:
    return sa.Column("user_id", sa.Uuid(), nullable=False)


def upgrade() -> None:
    # --- agent_runs -----------------------------------------------------------
    json_obj, json_arr = sa.text("'{}'"), sa.text("'[]'")
    for col in (
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("models", sa.JSON(), nullable=False, server_default=json_obj),
        sa.Column("status_reason", sa.String(512)),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_step", sa.String(64)),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "pending_questions", sa.JSON(), nullable=False, server_default=json_arr
        ),
        sa.Column("max_pages", sa.Integer()),
        sa.Column("guidance", sa.JSON()),
        sa.Column("reject_reasons", sa.JSON(), nullable=False, server_default=json_arr),
        sa.Column("reject_note", sa.Text()),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("timings", sa.JSON(), nullable=False, server_default=json_obj),
        sa.Column("event_seq", sa.Integer(), nullable=False, server_default="0"),
    ):  # fmt: skip
        _add("agent_runs", col)

    if "updated_at" not in _cols("agent_runs"):
        # SQLite cannot add a NOT NULL column with a non-constant default to a table
        # that has rows, so add it empty, backfill from created_at, then tighten it.
        op.add_column("agent_runs", sa.Column("updated_at", sa.DateTime(timezone=True)))
        op.execute("UPDATE agent_runs SET updated_at = created_at")
        with op.batch_alter_table("agent_runs") as batch:
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )

    op.execute(
        "UPDATE agent_runs SET status='waiting_for_user' WHERE status='awaiting_input'"
    )
    if "uq_agent_runs_active_job" in _indexes("agent_runs"):
        op.drop_index("uq_agent_runs_active_job", table_name="agent_runs")
    _index(
        "uq_agent_runs_active_job",
        "agent_runs",
        ["job_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE),
        postgresql_where=sa.text(ACTIVE),
    )
    _index(
        "ix_agent_runs_user_status_created",
        "agent_runs",
        ["user_id", "status", "created_at"],
    )
    _index("ix_agent_runs_user_created", "agent_runs", ["user_id", "created_at"])

    # --- run_events -----------------------------------------------------------
    t = _tables()
    if "run_events" not in t:
        op.create_table(
            "run_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "run_id",
                sa.String(32),
                sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            _uuid_user(),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("run_id", "seq"),
        )
    _index("ix_run_events_run_id", "run_events", ["run_id"])
    _index("ix_run_events_user_id", "run_events", ["user_id"])

    # --- drafts ---------------------------------------------------------------
    if "drafts" not in t:
        op.create_table(
            "drafts",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "run_id",
                sa.String(32),
                sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            _uuid_user(),
            sa.Column("iteration", sa.Integer(), nullable=False),
            sa.Column("tailored", sa.JSON(), nullable=False),
            sa.Column("violations", sa.JSON(), nullable=False),
            sa.Column("coverage", sa.JSON(), nullable=False),
            sa.Column("pages", sa.JSON(), nullable=False),
            sa.Column("outcome", sa.Text()),
            sa.Column("pdf_key", sa.String(512)),
            sa.Column("edited", sa.Boolean(), nullable=False),
            sa.Column("rev", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("run_id", "iteration"),
        )
    _index("ix_drafts_run_id", "drafts", ["run_id"])
    _index("ix_drafts_user_id", "drafts", ["user_id"])

    # --- approvals ------------------------------------------------------------
    if "approvals" not in t:
        op.create_table(
            "approvals",
            sa.Column("id", sa.String(32), primary_key=True),
            _uuid_user(),
            sa.Column(
                "run_id",
                sa.String(32),
                sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("job_id", sa.String(32), nullable=False),
            sa.Column("decision", sa.String(8), nullable=False),
            sa.Column("reasons", sa.JSON(), nullable=False),
            sa.Column("edits_applied", sa.Boolean(), nullable=False),
            sa.Column("final", sa.JSON()),
            sa.Column("pdf_key", sa.String(512)),
            sa.Column("file_name", sa.String(255)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("run_id"),
        )
    _index("ix_approvals_user_created", "approvals", ["user_id", "created_at"])

    # --- tracker_cards --------------------------------------------------------
    if "tracker_cards" not in t:
        op.create_table(
            "tracker_cards",
            sa.Column("id", sa.String(32), primary_key=True),
            _uuid_user(),
            sa.Column(
                "job_id",
                sa.String(32),
                sa.ForeignKey("jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("column", sa.String(16), nullable=False),
            sa.Column("position", sa.Float(), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True)),
            sa.Column("notes", sa.Text()),
            sa.Column("history", sa.JSON(), nullable=False),
            sa.Column("rev", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index(
        "ix_tracker_user_column_position",
        "tracker_cards",
        ["user_id", "column", "position"],
    )
    _index("uq_tracker_user_job", "tracker_cards", ["user_id", "job_id"], unique=True)

    # --- account --------------------------------------------------------------
    if "consent_log" not in t:
        op.create_table(
            "consent_log",
            sa.Column("id", sa.String(32), primary_key=True),
            _uuid_user(),
            sa.Column("policy_version", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_consent_user_created", "consent_log", ["user_id", "created_at"])

    if "exports" not in t:
        op.create_table(
            "exports",
            sa.Column("id", sa.String(32), primary_key=True),
            _uuid_user(),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("storage_key", sa.String(512)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ready_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
        )
    _index("ix_exports_user_id", "exports", ["user_id"])

    if "deletion_audit" not in t:
        op.create_table(
            "deletion_audit",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("sub_hash", sa.String(64), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        )
    _index("ix_deletion_audit_sub_hash", "deletion_audit", ["sub_hash"])

    _add("user_answers", sa.Column("detail", sa.Text()))
    for col in (
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("sessions_valid_after", sa.DateTime(timezone=True)),
        sa.Column("preferences", sa.JSON()),
        sa.Column("preferences_rev", sa.Integer(), nullable=False, server_default="0"),
    ):
        _add("users", col)


def downgrade() -> None:
    old = "status IN ('queued','running','awaiting_input')"
    op.execute(
        "UPDATE agent_runs SET status='awaiting_input' WHERE status='waiting_for_user'"
    )
    if "uq_agent_runs_active_job" in _indexes("agent_runs"):
        op.drop_index("uq_agent_runs_active_job", table_name="agent_runs")
    _index(
        "uq_agent_runs_active_job",
        "agent_runs",
        ["job_id"],
        unique=True,
        sqlite_where=sa.text(old),
        postgresql_where=sa.text(old),
    )
    for table in (
        "deletion_audit",
        "exports",
        "consent_log",
        "tracker_cards",
        "approvals",
        "drafts",
        "run_events",
    ):
        if table in _tables():
            op.drop_table(table)
    for table, names in (
        ("users", ["preferences_rev", "preferences", "sessions_valid_after", "status"]),
        ("user_answers", ["detail"]),
        (
            "agent_runs",
            [
                "updated_at", "event_seq", "timings", "cost_usd", "reject_note",
                "reject_reasons", "guidance", "max_pages", "pending_questions",
                "iteration", "current_step", "flagged", "status_reason", "models",
                "prompt_version",
            ],
        ),
    ):  # fmt: skip
        present = [n for n in names if n in _cols(table)]
        if present:
            with op.batch_alter_table(table) as batch:
                for n in present:
                    batch.drop_column(n)
