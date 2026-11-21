"""Training-data consent. Append-only: the current state is the latest row.

Revoking (enabled=false) excludes the user from FUTURE dataset snapshots only.
Snapshots already written are scrubbed, carry no user ids and cannot be traced back
to a user, so they are not rewritten.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.training import TrainingConsentLog
from app.repositories.manager import RepositoryManager
from app.schemas.training import TrainingConsentOut

log = logging.getLogger(__name__)


def latest_consent(session: Session, user_id: uuid.UUID) -> TrainingConsentLog | None:
    return session.scalar(
        select(TrainingConsentLog)
        .where(TrainingConsentLog.user_id == user_id)
        .order_by(TrainingConsentLog.id.desc())
        .limit(1)
    )


def consented_users(session: Session) -> dict[uuid.UUID, str]:
    """user_id -> policy_version for every user whose latest row is enabled."""
    latest = (
        select(
            TrainingConsentLog.user_id, func.max(TrainingConsentLog.id).label("max_id")
        )
        .group_by(TrainingConsentLog.user_id)
        .subquery()
    )
    rows = session.execute(
        select(TrainingConsentLog.user_id, TrainingConsentLog.policy_version)
        .join(latest, TrainingConsentLog.id == latest.c.max_id)
        .where(TrainingConsentLog.enabled.is_(True))
    )
    return {uid: version for uid, version in rows}


class TrainingService:
    def __init__(self, repos: RepositoryManager) -> None:
        self.session = repos.session

    def get(self, user_id: uuid.UUID) -> TrainingConsentOut:
        row = latest_consent(self.session, user_id)
        if row is None:
            return TrainingConsentOut(enabled=False)
        return TrainingConsentOut(
            enabled=row.enabled, policy_version=row.policy_version, at=row.created_at
        )

    def set(
        self, user_id: uuid.UUID, enabled: bool, policy_version: str
    ) -> TrainingConsentOut:
        row = latest_consent(self.session, user_id)
        # Repeating the current state is a no-op, so retries do not bloat the log.
        if row is None or (row.enabled, row.policy_version) != (
            enabled,
            policy_version,
        ):
            row = TrainingConsentLog(
                user_id=user_id, enabled=enabled, policy_version=policy_version
            )
            self.session.add(row)
            self.session.commit()
            log.info("training consent user=%s enabled=%s", user_id, enabled)
        return TrainingConsentOut(
            enabled=row.enabled, policy_version=row.policy_version, at=row.created_at
        )
