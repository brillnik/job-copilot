import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.models.job import AgentRun, Job, RunQuota, UserAnswer
from app.models.run import Approval, Draft, RunEvent
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[AgentRun]):
    """Every query takes user_id. Methods named stage_* never commit; the service does."""

    model = AgentRun

    def get_for_user(self, user_id: uuid.UUID, run_id: str) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        job_id: str | None,
        offset: int,
        limit: int,
    ) -> list[AgentRun]:
        stmt = select(AgentRun).where(AgentRun.user_id == user_id)
        if status:
            stmt = stmt.where(AgentRun.status == status)
        if job_id:
            stmt = stmt.where(AgentRun.job_id == job_id)
        stmt = (
            stmt.order_by(AgentRun.created_at.desc(), AgentRun.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def jobs_for(self, user_id: uuid.UUID, job_ids: list[str]) -> dict[str, Job]:
        rows = self.session.scalars(
            select(Job).where(Job.user_id == user_id, Job.id.in_(job_ids))
        )
        return {j.id: j for j in rows}

    # --- status / events -----------------------------------------------------
    def stage_cas_status(
        self, run: AgentRun, to: str, reason: str | None, step: str | None
    ) -> bool:
        """Move `run` to `to` only if it is still in the status we last saw."""
        values: dict = {"status": to, "status_reason": reason}
        if step is not None:
            values["current_step"] = step
        taken = self.session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run.id,
                AgentRun.user_id == run.user_id,
                AgentRun.status == run.status,
            )
            .values(**values, updated_at=datetime.now(UTC))
        ).rowcount
        return bool(taken)

    def stage_event(
        self, run: AgentRun, type_: str, payload: dict | None = None
    ) -> RunEvent:
        """Append to the run's log; seq comes from an atomic counter on the run row."""
        seq = self.session.execute(
            update(AgentRun)
            .where(AgentRun.id == run.id)
            .values(event_seq=AgentRun.event_seq + 1)
            .returning(AgentRun.event_seq)
        ).scalar_one()
        ev = RunEvent(
            run_id=run.id,
            user_id=run.user_id,
            seq=seq,
            type=type_,
            payload=payload or {},
        )
        self.session.add(ev)
        return ev

    def events_after(
        self, user_id: uuid.UUID, run_id: str, after: int, limit: int = 200
    ) -> list[RunEvent]:
        return list(
            self.session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.user_id == user_id,
                    RunEvent.seq > after,
                )
                .order_by(RunEvent.seq)
                .limit(limit)
            )
        )

    def status_of(self, user_id: uuid.UUID, run_id: str) -> str | None:
        """Fresh status straight from the database (bypasses the identity map)."""
        return self.session.scalar(
            select(AgentRun.status)
            .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
            .execution_options(populate_existing=True)
        )

    # --- quota ---------------------------------------------------------------
    def stage_release_quota(self, user_id: uuid.UUID, day: str) -> None:
        self.session.execute(
            update(RunQuota)
            .where(RunQuota.user_id == user_id, RunQuota.day == day, RunQuota.used > 0)
            .values(used=RunQuota.used - 1)
        )

    # --- drafts --------------------------------------------------------------
    def latest_draft(self, user_id: uuid.UUID, run_id: str) -> Draft | None:
        return self.session.scalar(
            select(Draft)
            .where(Draft.run_id == run_id, Draft.user_id == user_id)
            .order_by(Draft.iteration.desc())
            .limit(1)
        )

    def drafts(self, user_id: uuid.UUID, run_id: str) -> list[Draft]:
        return list(
            self.session.scalars(
                select(Draft)
                .where(Draft.run_id == run_id, Draft.user_id == user_id)
                .order_by(Draft.iteration)
            )
        )

    def latest_drafts(self, user_id: uuid.UUID, run_ids: list[str]) -> dict[str, Draft]:
        """The newest draft of each run, in one query."""
        if not run_ids:
            return {}
        newest = (
            select(Draft.run_id, func.max(Draft.iteration).label("it"))
            .where(Draft.user_id == user_id, Draft.run_id.in_(run_ids))
            .group_by(Draft.run_id)
            .subquery()
        )
        rows = self.session.scalars(
            select(Draft).join(
                newest,
                (Draft.run_id == newest.c.run_id) & (Draft.iteration == newest.c.it),
            )
        )
        return {d.run_id: d for d in rows}

    def stage_save_draft(self, draft: Draft) -> Draft:
        self.session.add(draft)
        return draft

    def cas_draft_rev(self, user_id: uuid.UUID, draft: Draft, expected: int) -> bool:
        """Atomically claim revision `expected` -> expected+1 (optimistic locking)."""
        taken = self.session.execute(
            update(Draft)
            .where(
                Draft.id == draft.id, Draft.user_id == user_id, Draft.rev == expected
            )
            .values(rev=expected + 1)
        ).rowcount
        if taken:
            self.session.refresh(draft)
        return bool(taken)

    # --- approvals -----------------------------------------------------------
    def approval_for(self, user_id: uuid.UUID, run_id: str) -> Approval | None:
        return self.session.scalar(
            select(Approval).where(
                Approval.run_id == run_id, Approval.user_id == user_id
            )
        )

    def stage_approval(self, approval: Approval) -> Approval:
        self.session.add(approval)
        return approval

    # --- answers -------------------------------------------------------------
    def stage_upsert_answer(
        self, user_id: uuid.UUID, skill: str, answer: str, detail: str | None
    ) -> UserAnswer:
        key = skill.strip().lower()
        row = self.session.scalar(
            select(UserAnswer).where(
                UserAnswer.user_id == user_id, func.lower(UserAnswer.skill) == key
            )
        )
        if row is None:
            row = UserAnswer(user_id=user_id, skill=key, answer=answer, detail=detail)
            self.session.add(row)
        else:
            row.answer, row.detail = answer, detail
            row.updated_at = datetime.now(UTC)
        return row

    def answers_full(self, user_id: uuid.UUID) -> list[tuple[str, str, str | None]]:
        rows = self.session.scalars(
            select(UserAnswer).where(UserAnswer.user_id == user_id)
        )
        return [(r.skill, r.answer, r.detail) for r in rows]
