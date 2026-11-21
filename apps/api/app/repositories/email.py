import uuid

from sqlalchemy import delete, func, select

from app.models.email import PENDING, EmailEvent, GmailConnection
from app.models.job import Job
from app.models.tracker import TrackerCard
from app.repositories.base import BaseRepository

WATCHED = ("applied", "response", "interview", "offer")


class EmailRepository(BaseRepository[EmailEvent]):
    """Every query takes user_id (the push lookup by address hash maps to a user)."""

    model = EmailEvent

    # --- connection ---------------------------------------------------------------
    def connection(self, user_id: uuid.UUID) -> GmailConnection | None:
        return self.session.scalar(
            select(GmailConnection).where(GmailConnection.user_id == user_id)
        )

    def connection_by_hash(self, email_hash: str) -> GmailConnection | None:
        return self.session.scalar(
            select(GmailConnection).where(GmailConnection.email_hash == email_hash)
        )

    def active_user_ids(self) -> list[uuid.UUID]:
        return list(
            self.session.scalars(
                select(GmailConnection.user_id).where(
                    GmailConnection.status == "active"
                )
            )
        )

    def stage_connection(self, conn: GmailConnection) -> GmailConnection:
        self.session.add(conn)
        return conn

    def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        self.session.execute(delete(EmailEvent).where(EmailEvent.user_id == user_id))
        self.session.execute(
            delete(GmailConnection).where(GmailConnection.user_id == user_id)
        )

    # --- events -------------------------------------------------------------------
    def known_message_ids(self, user_id: uuid.UUID, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        return set(
            self.session.scalars(
                select(EmailEvent.gmail_message_id).where(
                    EmailEvent.user_id == user_id,
                    EmailEvent.gmail_message_id.in_(ids),
                )
            )
        )

    def stage_event(self, event: EmailEvent) -> EmailEvent:
        self.session.add(event)
        return event

    def event(self, user_id: uuid.UUID, event_id: str) -> EmailEvent | None:
        return self.session.scalar(
            select(EmailEvent).where(
                EmailEvent.user_id == user_id, EmailEvent.id == event_id
            )
        )

    def suggestions(self, user_id: uuid.UUID, status: str | None = PENDING):
        """(event, company, title) for suggestions, newest first."""
        stmt = (
            select(EmailEvent, Job.company, Job.title)
            .outerjoin(Job, Job.id == EmailEvent.job_id)
            .where(
                EmailEvent.user_id == user_id, EmailEvent.suggestion_status.is_not(None)
            )
        )
        if status:
            stmt = stmt.where(EmailEvent.suggestion_status == status)
        return self.session.execute(
            stmt.order_by(EmailEvent.received_at.desc(), EmailEvent.id)
        ).all()

    def pending_count(self, user_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.count()).where(
                    EmailEvent.user_id == user_id,
                    EmailEvent.suggestion_status == PENDING,
                )
            )
            or 0
        )

    # --- tracker candidates -------------------------------------------------------
    def watched_cards(self, user_id: uuid.UUID):
        """(card_id, job_id, company, title, column) for cards that can get replies."""
        return self.session.execute(
            select(
                TrackerCard.id,
                TrackerCard.job_id,
                Job.company,
                Job.title,
                TrackerCard.column,
            )
            .join(Job, Job.id == TrackerCard.job_id)
            .where(
                TrackerCard.user_id == user_id,
                Job.user_id == user_id,
                TrackerCard.column.in_(WATCHED),
            )
        ).all()
