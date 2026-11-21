import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.application import (
    ACTIVE,
    Application,
    ApplyQuota,
    AtsHourlyQuota,
    SiteState,
)
from app.models.job import AgentRun, Job
from app.models.user import User
from app.repositories.base import BaseRepository

TOTAL = "*"  # ApplyQuota.site value for a user's all-sites total


class CapReached(Exception):
    """A cap blocked the slot; `scope` is user_day | site_day | ats_hour."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope


@dataclass(frozen=True)
class Caps:
    user_day: int
    site_day: int
    ats_hour: int | None  # None: no ATS counter (extension sites)


class ApplicationRepository(BaseRepository[Application]):
    """Every query takes user_id. stage_* methods never commit."""

    model = Application

    # --- rows ---------------------------------------------------------------
    def get_for_user(self, user_id: uuid.UUID, app_id: str) -> Application | None:
        return self.session.scalar(
            select(Application).where(
                Application.id == app_id, Application.user_id == user_id
            )
        )

    def status_of(self, user_id: uuid.UUID, app_id: str) -> str | None:
        """Fresh status straight from the database (bypasses the identity map)."""
        return self.session.scalar(
            select(Application.status)
            .where(Application.id == app_id, Application.user_id == user_id)
            .execution_options(populate_existing=True)
        )

    def by_job(self, user_id: uuid.UUID, job_id: str) -> Application | None:
        return self.session.scalar(
            select(Application).where(
                Application.user_id == user_id, Application.job_id == job_id
            )
        )

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
    ) -> list[Application]:
        stmt = select(Application).where(Application.user_id == user_id)
        if status:
            stmt = stmt.where(Application.status == status)
        return list(
            self.session.scalars(
                stmt.order_by(Application.created_at.desc(), Application.id)
                .offset(offset)
                .limit(limit)
            )
        )

    def updated_between(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[Application]:
        return list(
            self.session.scalars(
                select(Application)
                .where(
                    Application.user_id == user_id,
                    Application.updated_at >= start,
                    Application.updated_at < end,
                )
                .order_by(Application.updated_at)
            )
        )

    def queued(
        self, channel: str, *, user_id: uuid.UUID | None = None, limit: int = 50
    ):
        stmt = select(Application).where(
            Application.status == "queued", Application.channel == channel
        )
        if user_id is not None:
            stmt = stmt.where(Application.user_id == user_id)
        return list(
            self.session.scalars(stmt.order_by(Application.created_at).limit(limit))
        )

    def active_for_user(self, user_id: uuid.UUID) -> list[Application]:
        return list(
            self.session.scalars(
                select(Application).where(
                    Application.user_id == user_id, Application.status.in_(ACTIVE)
                )
            )
        )

    def cas_status(
        self,
        app: Application,
        allowed_from: tuple[str, ...],
        to: str,
        **values,
    ) -> bool:
        """Move to `to` only if still in one of `allowed_from`; stages, never commits."""
        taken = self.session.execute(
            update(Application)
            .where(
                Application.id == app.id,
                Application.user_id == app.user_id,
                Application.status.in_(allowed_from),
            )
            .values(status=to, updated_at=datetime.now(UTC), **values)
        ).rowcount
        if taken:
            self.session.refresh(app)
        return bool(taken)

    # --- caps -----------------------------------------------------------------
    def _ensure(self, model, **keys) -> None:
        if self.session.get(model, tuple(keys.values())) is not None:
            return
        self.session.add(model(**keys, used=0))
        try:
            self.session.commit()
        except IntegrityError:  # another worker created it first
            self.session.rollback()

    def used(self, user_id: uuid.UUID, day: str, site: str) -> int:
        row = self.session.get(ApplyQuota, (user_id, day, site))
        if row is not None:
            self.session.refresh(row)
        return row.used if row else 0

    def ats_used(self, ats: str, hour: str) -> int:
        row = self.session.get(AtsHourlyQuota, (ats, hour))
        if row is not None:
            self.session.refresh(row)
        return row.used if row else 0

    def has_room(
        self,
        user_id: uuid.UUID,
        day: str,
        hour: str,
        site: str,
        ats: str | None,
        caps: Caps,
    ) -> str | None:
        """None when a slot is free right now, else the scope that is full (a hint:
        only `reserve` is atomic)."""
        if self.used(user_id, day, TOTAL) >= caps.user_day:
            return "user_day"
        if self.used(user_id, day, site) >= caps.site_day:
            return "site_day"
        if (
            ats
            and caps.ats_hour is not None
            and self.ats_used(ats, hour) >= caps.ats_hour
        ):
            return "ats_hour"
        return None

    def reserve(self, app: Application, *, day: str, hour: str, caps: Caps) -> None:
        """Atomically take one slot in every applicable counter, or none at all.

        Each counter is a conditional UPDATE (`used < cap`), so concurrent callers at
        the boundary cannot both pass; if a later counter is full the transaction is
        rolled back, which also returns the earlier slots. Idempotent per application.
        """
        if app.slot_held:
            return
        uid, site, ats = app.user_id, app.site, app.ats
        self._ensure(ApplyQuota, user_id=uid, day=day, site=TOTAL)
        self._ensure(ApplyQuota, user_id=uid, day=day, site=site)
        use_ats = bool(ats) and ats != "unknown" and caps.ats_hour is not None
        if use_ats:
            self._ensure(AtsHourlyQuota, ats=ats, hour=hour)

        def take(model, cap: int, *where) -> bool:
            return bool(
                self.session.execute(
                    update(model)
                    .where(*where, model.used < cap)
                    .values(used=model.used + 1)
                ).rowcount
            )

        steps = [
            (
                "user_day",
                take(
                    ApplyQuota,
                    caps.user_day,
                    ApplyQuota.user_id == uid,
                    ApplyQuota.day == day,
                    ApplyQuota.site == TOTAL,
                ),
            )
        ]
        if steps[0][1]:
            steps.append(
                (
                    "site_day",
                    take(
                        ApplyQuota,
                        caps.site_day,
                        ApplyQuota.user_id == uid,
                        ApplyQuota.day == day,
                        ApplyQuota.site == site,
                    ),
                )
            )
        if all(ok for _, ok in steps) and use_ats:
            steps.append(
                (
                    "ats_hour",
                    take(
                        AtsHourlyQuota, caps.ats_hour or 0,
                        AtsHourlyQuota.ats == ats, AtsHourlyQuota.hour == hour,
                    ),
                )
            )  # fmt: skip
        for scope, ok in steps:
            if not ok:
                self.session.rollback()
                raise CapReached(scope)
        self.session.execute(
            update(Application)
            .where(Application.id == app.id, Application.user_id == uid)
            .values(slot_held=True, slot_day=day, slot_hour=hour if use_ats else None)
        )
        self.session.commit()
        self.session.refresh(app)

    def reserve_ats(self, app: Application, ats: str, hour: str, cap: int) -> None:
        """Take the per-ATS hourly slot once the page revealed the real ATS
        (Himalayas links only say which ATS after they open)."""
        if app.slot_hour:
            return
        self._ensure(AtsHourlyQuota, ats=ats, hour=hour)
        taken = self.session.execute(
            update(AtsHourlyQuota)
            .where(
                AtsHourlyQuota.ats == ats,
                AtsHourlyQuota.hour == hour,
                AtsHourlyQuota.used < cap,
            )
            .values(used=AtsHourlyQuota.used + 1)
        ).rowcount
        if not taken:
            self.session.rollback()
            raise CapReached("ats_hour")
        self.session.execute(
            update(Application)
            .where(Application.id == app.id, Application.user_id == app.user_id)
            .values(ats=ats, slot_hour=hour)
        )
        self.session.commit()
        self.session.refresh(app)

    def stage_release(self, app: Application) -> None:
        """Give the slot back (skipped, failed or cancelled: only submits count)."""
        if not app.slot_held:
            return
        sites = (TOTAL, app.site)
        self.session.execute(
            update(ApplyQuota)
            .where(
                ApplyQuota.user_id == app.user_id,
                ApplyQuota.day == app.slot_day,
                ApplyQuota.site.in_(sites),
                ApplyQuota.used > 0,
            )
            .values(used=ApplyQuota.used - 1)
        )
        if app.slot_hour and app.ats:
            self.session.execute(
                update(AtsHourlyQuota)
                .where(
                    AtsHourlyQuota.ats == app.ats,
                    AtsHourlyQuota.hour == app.slot_hour,
                    AtsHourlyQuota.used > 0,
                )
                .values(used=AtsHourlyQuota.used - 1)
            )
        app.slot_held = False

    # --- site state -------------------------------------------------------------
    def state(self, user_id: uuid.UUID, site: str) -> SiteState | None:
        row = self.session.get(SiteState, (user_id, site))
        if row is not None:
            self.session.refresh(row)
        return row

    def paused_sites(self, user_id: uuid.UUID) -> list[str]:
        return list(
            self.session.scalars(
                select(SiteState.site).where(
                    SiteState.user_id == user_id, SiteState.paused_at.is_not(None)
                )
            )
        )

    def record_block(
        self, user_id: uuid.UUID, site: str, reason: str, pause_after: int
    ) -> bool:
        """Count one more consecutive block; True when this paused the site."""
        if self.session.get(SiteState, (user_id, site)) is None:
            self.session.add(
                SiteState(user_id=user_id, site=site, consecutive_blocks=0)
            )
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
        n = self.session.execute(
            update(SiteState)
            .where(SiteState.user_id == user_id, SiteState.site == site)
            .values(
                consecutive_blocks=SiteState.consecutive_blocks + 1, last_reason=reason
            )
            .returning(SiteState.consecutive_blocks)
        ).scalar_one()
        paused = n >= pause_after
        if paused:
            self.session.execute(
                update(SiteState)
                .where(
                    SiteState.user_id == user_id,
                    SiteState.site == site,
                    SiteState.paused_at.is_(None),
                )
                .values(paused_at=datetime.now(UTC))
            )
        self.session.commit()
        return paused

    def reset_blocks(
        self, user_id: uuid.UUID, site: str, *, unpause: bool = False
    ) -> None:
        values: dict = {"consecutive_blocks": 0}
        if unpause:
            values["paused_at"] = None
        self.session.execute(
            update(SiteState)
            .where(SiteState.user_id == user_id, SiteState.site == site)
            .values(**values)
        )

    def count_by_status(self, user_id: uuid.UUID) -> dict[str, int]:
        rows = self.session.execute(
            select(Application.status, func.count())
            .where(Application.user_id == user_id)
            .group_by(Application.status)
        )
        return {s: n for s, n in rows}

    # --- autopilot ----------------------------------------------------------
    def autopilot_user_ids(self) -> list[uuid.UUID]:
        return [
            u.id
            for u in self.session.scalars(
                select(User).where(User.status == "active", User.autopilot.is_not(None))
            )
        ]

    def untailored_recommended_jobs(
        self, user_id: uuid.UUID, min_score: int
    ) -> list[Job]:
        """Saved-from-recommendation jobs that are ready but have no run yet."""
        has_run = select(AgentRun.job_id).where(AgentRun.user_id == user_id)
        return list(
            self.session.scalars(
                select(Job)
                .where(
                    Job.user_id == user_id,
                    Job.source_channel == "recommended",
                    Job.status == "new",
                    Job.score >= min_score,
                    Job.id.not_in(has_run),
                )
                .order_by(Job.score.desc(), Job.id)
            )
        )

    def autopilot_runs(
        self, user_id: uuid.UUID, statuses: tuple[str, ...]
    ) -> list[AgentRun]:
        return list(
            self.session.scalars(
                select(AgentRun).where(
                    AgentRun.user_id == user_id,
                    AgentRun.autopilot.is_(True),
                    AgentRun.status.in_(statuses),
                )
            )
        )
