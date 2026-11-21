"""discovery catalogue, recommendations, extension tokens; jobs.{catalog_job_id,source_channel}

Adds companies, catalog_jobs (shared, no user_id), recommendations, extension_tokens,
extension_pairing_codes and two columns on jobs.

Idempotent: every object is created only if missing.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
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


def _dt(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    json_arr = sa.text("'[]'")

    # --- jobs -------------------------------------------------------------------
    if "catalog_job_id" not in _cols("jobs"):
        op.add_column("jobs", sa.Column("catalog_job_id", sa.String(32)))
    if "source_channel" not in _cols("jobs"):
        op.add_column(
            "jobs",
            sa.Column(
                "source_channel",
                sa.String(16),
                nullable=False,
                server_default="manual",
            ),
        )
    _index("ix_jobs_catalog_job_id", "jobs", ["catalog_job_id"])

    t = _tables()
    # --- companies ----------------------------------------------------------------
    if "companies" not in t:
        op.create_table(
            "companies",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("name_key", sa.String(255), nullable=False, unique=True),
            sa.Column("careers_url", sa.String(2048)),
            sa.Column("ats", sa.String(16), nullable=False),
            sa.Column("board_token", sa.String(255)),
            sa.Column("lists", sa.JSON(), nullable=False, server_default=json_arr),
            _dt("last_detected_at"),
            sa.Column(
                "redetect", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            _dt("created_at", False),
            sa.UniqueConstraint("ats", "board_token"),
        )

    # --- catalog_jobs ---------------------------------------------------------------
    if "catalog_jobs" not in t:
        op.create_table(
            "catalog_jobs",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=False),
            sa.Column(
                "company_id",
                sa.String(32),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("location", sa.String(512)),
            sa.Column("city", sa.String(128)),
            sa.Column(
                "remote", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "country_restrictions",
                sa.JSON(),
                nullable=False,
                server_default=json_arr,
            ),
            sa.Column("apply_url", sa.String(2048), nullable=False),
            sa.Column("source_attribution", sa.JSON()),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("jd", sa.JSON()),
            sa.Column("embedding", sa.JSON()),
            sa.Column("embedding_model", sa.String(64)),
            sa.Column("duplicate_of", sa.String(32)),
            _dt("first_seen", False),
            _dt("last_seen", False),
            _dt("closed_at"),
            sa.UniqueConstraint("source", "external_id"),
        )
    _index("ix_catalog_jobs_company_id", "catalog_jobs", ["company_id"])
    _index(
        "ix_catalog_jobs_closed_last_seen", "catalog_jobs", ["closed_at", "last_seen"]
    )

    # --- recommendations -------------------------------------------------------------
    if "recommendations" not in t:
        op.create_table(
            "recommendations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "catalog_job_id",
                sa.String(32),
                sa.ForeignKey("catalog_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("reasons", sa.JSON(), nullable=False, server_default=json_arr),
            sa.Column("digest_date", sa.String(10), nullable=False),
            sa.Column("action", sa.String(16), nullable=False, server_default="none"),
            sa.Column("dismiss_reason", sa.String(200)),
            sa.Column("job_id", sa.String(32)),
            _dt("created_at", False),
            sa.UniqueConstraint("user_id", "catalog_job_id", "digest_date"),
        )
    _index("ix_recommendations_user_id", "recommendations", ["user_id"])
    _index("ix_recommendations_catalog_job_id", "recommendations", ["catalog_job_id"])
    _index(
        "ix_recommendations_user_digest",
        "recommendations",
        ["user_id", "digest_date"],
    )

    # --- extension tokens / pairing codes ----------------------------------------------
    if "extension_tokens" not in t:
        op.create_table(
            "extension_tokens",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("device_name", sa.String(120)),
            _dt("created_at", False),
            _dt("last_used_at"),
            _dt("revoked_at"),
        )
    _index("ix_extension_tokens_user_id", "extension_tokens", ["user_id"])

    if "extension_pairing_codes" not in t:
        op.create_table(
            "extension_pairing_codes",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
            _dt("expires_at", False),
            _dt("used_at"),
            _dt("created_at", False),
        )
    _index("ix_extension_pairing_codes_user_id", "extension_pairing_codes", ["user_id"])


def downgrade() -> None:
    for table in (
        "extension_pairing_codes",
        "extension_tokens",
        "recommendations",
        "catalog_jobs",
        "companies",
    ):
        if table in _tables():
            op.drop_table(table)
    if "ix_jobs_catalog_job_id" in _indexes("jobs"):
        op.drop_index("ix_jobs_catalog_job_id", table_name="jobs")
    with op.batch_alter_table("jobs") as batch:
        for col in ("source_channel", "catalog_job_id"):
            if col in _cols("jobs"):
                batch.drop_column(col)
