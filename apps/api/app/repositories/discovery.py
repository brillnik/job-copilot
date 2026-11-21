import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.clock import as_utc
from app.models.discovery import (
    CatalogJob,
    Company,
    ExtensionPairingCode,
    ExtensionToken,
    Recommendation,
)
from app.models.job import Job
from app.repositories.base import BaseRepository


class CatalogRepository(BaseRepository[CatalogJob]):
    """Shared tables: no user_id. Written by discovery workers only."""

    model = CatalogJob

    def company(self, company_id: str) -> Company | None:
        return self.session.get(Company, company_id)

    def companies_with_ats(self) -> list[Company]:
        return list(
            self.session.scalars(
                select(Company)
                .where(Company.ats != "unknown", Company.board_token.is_not(None))
                .order_by(Company.name_key)
            )
        )

    def companies_to_detect(self, stale_before: datetime) -> list[Company]:
        return list(
            self.session.scalars(
                select(Company)
                .where(
                    Company.careers_url.is_not(None),
                    (Company.last_detected_at.is_(None))
                    | (Company.last_detected_at < stale_before)
                    | (Company.redetect.is_(True)),
                )
                .order_by(Company.name_key)
            )
        )

    def company_by_key(self, key: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.name_key == key))

    def get_job(self, source: str, external_id: str) -> CatalogJob | None:
        return self.session.scalar(
            select(CatalogJob).where(
                CatalogJob.source == source, CatalogJob.external_id == external_id
            )
        )

    def by_id(self, catalog_job_id: str) -> CatalogJob | None:
        return self.session.get(CatalogJob, catalog_job_id)

    def by_ids(self, ids: list[str]) -> dict[str, CatalogJob]:
        if not ids:
            return {}
        rows = self.session.scalars(select(CatalogJob).where(CatalogJob.id.in_(ids)))
        return {r.id: r for r in rows}

    def needing_enrichment(self, embedder_name: str, limit: int) -> list[CatalogJob]:
        return list(
            self.session.scalars(
                select(CatalogJob)
                .where(
                    CatalogJob.closed_at.is_(None),
                    (CatalogJob.jd.is_(None))
                    | (CatalogJob.embedding.is_(None))
                    | (CatalogJob.embedding_model != embedder_name),
                )
                .order_by(CatalogJob.first_seen)
                .limit(limit)
            )
        )

    def by_content_hash(self, content_hash: str) -> CatalogJob | None:
        """Any row with this text that already has a JD (extract-once reuse)."""
        return self.session.scalar(
            select(CatalogJob)
            .where(CatalogJob.content_hash == content_hash, CatalogJob.jd.is_not(None))
            .limit(1)
        )

    def open_jobs(self) -> list[CatalogJob]:
        return list(
            self.session.scalars(
                select(CatalogJob).where(CatalogJob.closed_at.is_(None))
            )
        )

    def stale_open(self, before: datetime) -> list[CatalogJob]:
        return list(
            self.session.scalars(
                select(CatalogJob).where(
                    CatalogJob.closed_at.is_(None), CatalogJob.last_seen < before
                )
            )
        )

    def searchable(self, since: datetime) -> list[CatalogJob]:
        """Open, enriched, non-duplicate rows first seen since `since`."""
        return list(
            self.session.scalars(
                select(CatalogJob).where(
                    CatalogJob.closed_at.is_(None),
                    CatalogJob.first_seen >= since,
                    CatalogJob.embedding.is_not(None),
                    CatalogJob.jd.is_not(None),
                    CatalogJob.duplicate_of.is_(None),
                )
            )
        )


class RecommendationRepository(BaseRepository[Recommendation]):
    """Every query takes user_id; another user's recommendation looks like none."""

    model = Recommendation

    def get_for_user(self, user_id: uuid.UUID, rec_id: str) -> Recommendation | None:
        return self.session.scalar(
            select(Recommendation).where(
                Recommendation.id == rec_id, Recommendation.user_id == user_id
            )
        )

    def digest(self, user_id: uuid.UUID, digest_date: str) -> list[Recommendation]:
        return list(
            self.session.scalars(
                select(Recommendation)
                .where(
                    Recommendation.user_id == user_id,
                    Recommendation.digest_date == digest_date,
                    Recommendation.action != "dismissed",
                )
                .order_by(Recommendation.score.desc(), Recommendation.id)
            )
        )

    def excluded_catalog_ids(self, user_id: uuid.UUID) -> set[str]:
        """Already saved or dismissed, or already a job of this user."""
        acted = self.session.scalars(
            select(Recommendation.catalog_job_id).where(
                Recommendation.user_id == user_id,
                Recommendation.action.in_(["saved", "dismissed"]),
            )
        )
        owned = self.session.scalars(
            select(Job.catalog_job_id).where(
                Job.user_id == user_id, Job.catalog_job_id.is_not(None)
            )
        )
        return set(acted) | set(owned)

    def replace_digest(
        self, user_id: uuid.UUID, digest_date: str, rows: list[Recommendation]
    ) -> None:
        """Rebuild is idempotent: unacted rows of the day are replaced, acted ones kept."""
        kept = set(
            self.session.scalars(
                select(Recommendation.catalog_job_id).where(
                    Recommendation.user_id == user_id,
                    Recommendation.digest_date == digest_date,
                    Recommendation.action != "none",
                )
            )
        )
        self.session.execute(
            delete(Recommendation).where(
                Recommendation.user_id == user_id,
                Recommendation.digest_date == digest_date,
                Recommendation.action == "none",
            )
        )
        self.session.add_all(r for r in rows if r.catalog_job_id not in kept)
        self.session.commit()

    def job_for_catalog(self, user_id: uuid.UUID, catalog_job_id: str) -> Job | None:
        return self.session.scalar(
            select(Job)
            .where(Job.user_id == user_id, Job.catalog_job_id == catalog_job_id)
            .limit(1)
        )


class ExtensionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_code(self, row: ExtensionPairingCode) -> None:
        self.session.add(row)
        self.session.commit()

    def consume_code(self, code_hash: str, now: datetime) -> uuid.UUID | None:
        """Atomically mark an unexpired, unused code as used; returns its user."""
        row = self.session.scalar(
            select(ExtensionPairingCode).where(
                ExtensionPairingCode.code_hash == code_hash
            )
        )
        if row is None:
            return None
        if row.used_at is not None or as_utc(row.expires_at) <= now:
            return None
        taken = self.session.execute(
            update(ExtensionPairingCode)
            .where(
                ExtensionPairingCode.id == row.id,
                ExtensionPairingCode.used_at.is_(None),
            )
            .values(used_at=now)
        ).rowcount
        self.session.commit()
        return row.user_id if taken else None

    def add_token(self, row: ExtensionToken) -> ExtensionToken:
        self.session.add(row)
        self.session.commit()
        return row

    def token_by_hash(self, token_hash: str) -> ExtensionToken | None:
        return self.session.scalar(
            select(ExtensionToken).where(ExtensionToken.token_hash == token_hash)
        )

    def tokens_for_user(self, user_id: uuid.UUID) -> list[ExtensionToken]:
        return list(
            self.session.scalars(
                select(ExtensionToken)
                .where(ExtensionToken.user_id == user_id)
                .order_by(ExtensionToken.created_at)
            )
        )

    def token_for_user(
        self, user_id: uuid.UUID, token_id: str
    ) -> ExtensionToken | None:
        return self.session.scalar(
            select(ExtensionToken).where(
                ExtensionToken.id == token_id, ExtensionToken.user_id == user_id
            )
        )
