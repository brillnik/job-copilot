import uuid
from datetime import datetime

from sqlalchemy import case, func, select, update

from app.models.job import Job
from app.models.tracker import TrackerCard
from app.repositories.base import BaseRepository

RESPONDED = ("response", "interview", "offer", "rejected")


class TrackerRepository(BaseRepository[TrackerCard]):
    """Every query takes user_id. Methods named stage_* never commit."""

    model = TrackerCard

    def get_for_user(self, user_id: uuid.UUID, card_id: str) -> TrackerCard | None:
        return self.session.scalar(
            select(TrackerCard).where(
                TrackerCard.id == card_id, TrackerCard.user_id == user_id
            )
        )

    def by_job(self, user_id: uuid.UUID, job_id: str) -> TrackerCard | None:
        return self.session.scalar(
            select(TrackerCard).where(
                TrackerCard.user_id == user_id, TrackerCard.job_id == job_id
            )
        )

    def column_cards(
        self, user_id: uuid.UUID, column: str, *, exclude: str | None = None
    ) -> list[TrackerCard]:
        stmt = select(TrackerCard).where(
            TrackerCard.user_id == user_id, TrackerCard.column == column
        )
        if exclude:
            stmt = stmt.where(TrackerCard.id != exclude)
        return list(
            self.session.scalars(stmt.order_by(TrackerCard.position, TrackerCard.id))
        )

    def last_position(self, user_id: uuid.UUID, column: str) -> float | None:
        return self.session.scalar(
            select(func.max(TrackerCard.position)).where(
                TrackerCard.user_id == user_id, TrackerCard.column == column
            )
        )

    def stage_add(self, card: TrackerCard) -> TrackerCard:
        self.session.add(card)
        return card

    def stage_delete(self, card: TrackerCard) -> None:
        self.session.delete(card)

    def cas_rev(self, user_id: uuid.UUID, card: TrackerCard, expected: int) -> bool:
        taken = self.session.execute(
            update(TrackerCard)
            .where(
                TrackerCard.id == card.id,
                TrackerCard.user_id == user_id,
                TrackerCard.rev == expected,
            )
            .values(rev=expected + 1)
        ).rowcount
        if taken:
            self.session.refresh(card)
        return bool(taken)

    def board(self, user_id: uuid.UUID):
        """(card, company, title, score) for every card, in column/position order."""
        return self.session.execute(
            select(TrackerCard, Job.company, Job.title, Job.score)
            .join(Job, Job.id == TrackerCard.job_id)
            .where(TrackerCard.user_id == user_id, Job.user_id == user_id)
            .order_by(TrackerCard.column, TrackerCard.position, TrackerCard.id)
        ).all()

    def counts(self, user_id: uuid.UUID) -> dict[str, int]:
        rows = self.session.execute(
            select(TrackerCard.column, func.count())
            .where(TrackerCard.user_id == user_id)
            .group_by(TrackerCard.column)
        )
        return {col: n for col, n in rows}

    def stats(
        self, user_id: uuid.UUID, *, week_start: datetime, window_start: datetime
    ) -> dict:
        """One aggregate query each; no cards are loaded into Python."""
        applied = TrackerCard.applied_at.is_not(None)
        row = self.session.execute(
            select(
                func.coalesce(
                    func.sum(case((TrackerCard.applied_at >= week_start, 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((TrackerCard.applied_at >= window_start, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (TrackerCard.applied_at >= window_start)
                                & TrackerCard.column.in_(RESPONDED),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(TrackerCard.user_id == user_id, applied)
        ).one()
        avg = self.session.scalar(
            select(func.avg(Job.score))
            .join(TrackerCard, TrackerCard.job_id == Job.id)
            .where(TrackerCard.user_id == user_id, Job.user_id == user_id)
        )
        return {
            "applied_this_week": int(row[0]),
            "applied_30d": int(row[1]),
            "responses_30d": int(row[2]),
            "avg_match_score": round(float(avg), 1) if avg is not None else None,
        }
