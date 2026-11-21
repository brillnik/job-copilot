import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.models.job import (
    ARCHIVED,
    RUN_ACTIVE,
    AgentRun,
    Event,
    ImageUpload,
    JdExtraction,
    Job,
    RunQuota,
    UserAnswer,
)
from app.models.run import RunEvent
from app.repositories.base import BaseRepository


class QuotaExceeded(Exception):
    def __init__(self, used: int) -> None:
        self.used = used


class RunInProgress(Exception):
    def __init__(self, run_id: str | None) -> None:
        self.run_id = run_id


class JobRepository(BaseRepository[Job]):
    """Every query takes user_id; a job of another user is indistinguishable from none."""

    model = Job

    def get_for_user(self, user_id: uuid.UUID, job_id: str) -> Job | None:
        return self.session.scalar(
            select(Job).where(Job.id == job_id, Job.user_id == user_id)
        )

    def find_duplicate(
        self, user_id: uuid.UUID, url: str | None, content_hash: str | None
    ) -> Job | None:
        conds = []
        if url:
            conds.append(Job.url == url)
        if content_hash:
            conds.append(Job.content_hash == content_hash)
        if not conds:
            return None
        return self.session.scalar(
            select(Job)
            .where(Job.user_id == user_id, or_(*conds))
            .order_by(Job.created_at)
            .limit(1)
        )

    def count_created_since(self, user_id: uuid.UUID, since: datetime) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.user_id == user_id, Job.created_at >= since)
            )
            or 0
        )

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        min_score: int | None,
        city: str | None,
        q: str | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> list[Job]:
        stmt = select(Job).where(Job.user_id == user_id)
        stmt = (
            stmt.where(Job.status == status)
            if status
            else stmt.where(Job.status != ARCHIVED)
        )
        if min_score is not None:
            stmt = stmt.where(Job.score >= min_score)
        if city:
            stmt = stmt.where(
                Job.id.in_(
                    select(JdExtraction.job_id).where(
                        JdExtraction.user_id == user_id,
                        func.lower(JdExtraction.jd["location"].as_string()).contains(
                            city.lower()
                        ),
                    )
                )
            )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Job.company).like(like), func.lower(Job.title).like(like)
                )
            )
        order = (
            [Job.score.is_(None), Job.score.desc()]
            if sort == "score"
            else [Job.created_at.desc()]
        )
        stmt = stmt.order_by(*order, Job.id).offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def extraction_for(self, user_id: uuid.UUID, job_id: str) -> JdExtraction | None:
        return self.session.scalar(
            select(JdExtraction).where(
                JdExtraction.job_id == job_id, JdExtraction.user_id == user_id
            )
        )

    def extractions_for(
        self, user_id: uuid.UUID, job_ids: list[str]
    ) -> dict[str, JdExtraction]:
        rows = self.session.scalars(
            select(JdExtraction).where(
                JdExtraction.user_id == user_id, JdExtraction.job_id.in_(job_ids)
            )
        )
        return {r.job_id: r for r in rows}

    def save_extraction(
        self, user_id: uuid.UUID, job_id: str, jd: dict, version: str
    ) -> JdExtraction:
        """Upsert, so re-running extraction overwrites and never duplicates."""
        row = self.extraction_for(user_id, job_id)
        if row is None:
            row = JdExtraction(
                job_id=job_id, user_id=user_id, jd=jd, extractor_version=version
            )
            self.session.add(row)
        else:
            row.jd, row.extractor_version = jd, version
            row.created_at = datetime.now(UTC)
        return row

    def rescorable(self, user_id: uuid.UUID) -> list[Job]:
        return list(
            self.session.scalars(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.status.in_(["new", "tailoring", "in_review"]),
                )
            )
        )

    def answers(self, user_id: uuid.UUID) -> dict[str, str]:
        rows = self.session.scalars(
            select(UserAnswer).where(UserAnswer.user_id == user_id)
        )
        return {r.skill.lower(): r.answer for r in rows}

    # --- runs ---------------------------------------------------------------
    def latest_run(self, user_id: uuid.UUID, job_id: str) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun)
            .where(AgentRun.user_id == user_id, AgentRun.job_id == job_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id)
            .limit(1)
        )

    def active_run(self, user_id: uuid.UUID, job_id: str) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun).where(
                AgentRun.user_id == user_id,
                AgentRun.job_id == job_id,
                AgentRun.status.in_(RUN_ACTIVE),
            )
        )

    def get_run(self, user_id: uuid.UUID, run_id: str) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )

    def reserve_run(
        self,
        user_id: uuid.UUID,
        job: Job,
        profile_version: int,
        day: str,
        cap: int,
        *,
        max_pages: int | None = None,
        guidance: dict | None = None,
        autopilot: bool = False,
    ) -> AgentRun:
        """Atomically take a daily-cap slot and create the run, in one transaction.

        The slot is a conditional UPDATE (`used < cap`), so concurrent requests at
        the boundary cannot both succeed. A second active run for the same job
        violates the partial unique index; the rollback also returns the slot.
        """
        self._ensure_quota_row(user_id, day)
        taken = self.session.execute(
            update(RunQuota)
            .where(
                RunQuota.user_id == user_id, RunQuota.day == day, RunQuota.used < cap
            )
            .values(used=RunQuota.used + 1)
        ).rowcount
        if not taken:
            self.session.rollback()
            raise QuotaExceeded(self.quota_used(user_id, day))
        run = AgentRun(
            id=uuid.uuid4().hex,
            user_id=user_id,
            job_id=job.id,
            profile_version=profile_version,
            max_pages=max_pages,
            guidance=guidance,
            autopilot=autopilot,
            event_seq=1,
        )
        self.session.add(run)
        self.session.add(
            RunEvent(
                run_id=run.id,
                user_id=user_id,
                seq=1,
                type="status",
                payload={"status": "queued", "from": None, "reason": None},
            )
        )
        job.status = "tailoring"
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            active = self.active_run(user_id, job.id)
            raise RunInProgress(active.id if active else None) from None
        return run

    def _ensure_quota_row(self, user_id: uuid.UUID, day: str) -> None:
        if self.session.get(RunQuota, (user_id, day)) is not None:
            return
        self.session.add(RunQuota(user_id=user_id, day=day, used=0))
        try:
            self.session.commit()
        except IntegrityError:  # another request created it first
            self.session.rollback()

    def quota_used(self, user_id: uuid.UUID, day: str) -> int:
        row = self.session.get(RunQuota, (user_id, day))
        if row is not None:
            self.session.refresh(row)
        return row.used if row else 0

    # --- events / images ----------------------------------------------------
    def add_event(self, user_id: uuid.UUID, type_: str, payload: dict) -> Event:
        ev = self.stage_event(user_id, type_, payload)
        self.session.commit()
        return ev

    def stage_event(self, user_id: uuid.UUID, type_: str, payload: dict) -> Event:
        ev = Event(user_id=user_id, type=type_, payload=payload)
        self.session.add(ev)
        return ev

    def events_after(self, user_id: uuid.UUID, after: int, limit: int) -> list[Event]:
        return list(
            self.session.scalars(
                select(Event)
                .where(Event.user_id == user_id, Event.id > after)
                .order_by(Event.id)
                .limit(limit)
            )
        )

    def get_image(self, user_id: uuid.UUID, image_id: str) -> ImageUpload | None:
        return self.session.scalar(
            select(ImageUpload).where(
                ImageUpload.id == image_id, ImageUpload.user_id == user_id
            )
        )


def hour_ago() -> datetime:
    return datetime.now(UTC) - timedelta(hours=1)
