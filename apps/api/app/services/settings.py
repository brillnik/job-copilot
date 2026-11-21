import logging
import uuid

from app.core.clock import local_day, next_reset
from app.core.config import settings as cfg
from app.core.exceptions import Conflict, NotFound
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.schemas.account import Preferences, SettingsOut
from app.services.prefs import preferences_of
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)

# Changing any of these changes job scores, so open jobs are re-scored (no LLM).
SCORING_FIELDS = ("cities", "expected_ctc_lpa", "target_roles")


class SettingsService:
    def __init__(self, repos: RepositoryManager, queue: TaskQueue) -> None:
        self.repos = repos
        self.queue = queue

    def _user(self, user_id: uuid.UUID) -> User:
        user = self.repos.users.get(user_id)
        if user is None:
            raise NotFound("User not found")
        return user

    def get(self, user_id: uuid.UUID) -> SettingsOut:
        user = self._user(user_id)
        prefs = preferences_of(user)
        return SettingsOut(
            preferences=prefs,
            configured=user.preferences is not None,
            rev=user.preferences_rev,
            runs_used_today=self.repos.jobs.quota_used(user_id, local_day()),
            daily_cap=min(prefs.daily_cap, cfg.daily_cap_max),
            cap_resets_at=next_reset(),
        )

    def put(
        self, user_id: uuid.UUID, body: Preferences, if_match: int | None
    ) -> SettingsOut:
        user = self._user(user_id)
        before = preferences_of(user).model_dump()
        expected = user.preferences_rev if if_match is None else if_match
        if not self.repos.users.cas_preferences_rev(user, expected):
            self.repos.session.rollback()
            self.repos.session.refresh(user)
            log.info("settings stale write user=%s", user_id)
            raise Conflict(
                "Your settings changed since you loaded them",
                code="stale_write",
                details={"rev": user.preferences_rev},
            )
        after = body.model_dump()
        user.preferences = after
        self.repos.session.commit()
        rescore = any(before[k] != after[k] for k in SCORING_FIELDS)
        if rescore:
            self.queue.enqueue("rescore_jobs", user_id=str(user_id))
        # Values (CTC, cities) are personal: log which fields moved, not what they are.
        log.info(
            "settings saved user=%s changed=%s rescore=%s",
            user_id,
            sorted(k for k in after if before.get(k) != after[k]),
            rescore,
        )
        return self.get(user_id)
