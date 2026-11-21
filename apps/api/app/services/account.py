"""/me: profile, consent, sign-out everywhere, data export, account deletion.

Logs carry ids and statuses only: never names, emails or token contents.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core import signing
from app.core.clock import as_utc
from app.core.config import settings
from app.core.exceptions import NotFound, Unauthorized
from app.models.account import ConsentLog, Export
from app.models.job import RUN_ACTIVE
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.schemas.account import Consent, ExportOut, MeOut
from app.services.identity import IdentityProvider
from app.services.run_state import IllegalTransition, transition
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)


class AccountService:
    def __init__(
        self,
        repos: RepositoryManager,
        queue: TaskQueue,
        idp: IdentityProvider,
    ) -> None:
        self.repos = repos
        self.queue = queue
        self.idp = idp

    # --- profile / consent ---------------------------------------------------
    def me(self, user: User) -> MeOut:
        latest = self.repos.accounts.latest_consent(user.id)
        provider = user.auth0_sub.split("|", 1)[0] if "|" in user.auth0_sub else None
        return MeOut(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_providers=[provider] if provider else [],
            consent=Consent(policy_version=latest.policy_version, at=latest.created_at)
            if latest
            else None,
            created_at=user.created_at,
        )

    def consent(self, user: User, policy_version: str) -> Consent:
        row = self.repos.accounts.stage_consent(
            ConsentLog(user_id=user.id, policy_version=policy_version)
        )
        self.repos.session.commit()
        log.info("consent recorded user=%s version=%s", user.id, policy_version)
        return Consent(policy_version=row.policy_version, at=row.created_at)

    # --- sessions ------------------------------------------------------------
    def logout_all(self, user: User) -> None:
        user.sessions_valid_after = datetime.now(UTC)
        self.repos.session.commit()
        try:
            self.idp.revoke_sessions(user.auth0_sub)
        except Exception as e:  # noqa: BLE001 - our own cut-off already holds
            log.error(
                "idp session revoke failed user=%s error=%s", user.id, type(e).__name__
            )
        log.info("all sessions revoked user=%s", user.id)

    # --- export --------------------------------------------------------------
    def request_export(self, user: User) -> str:
        pending = self.repos.accounts.pending_export(user.id)
        if pending is not None:  # one at a time; a retry gets the same id
            return pending.id
        export = self.repos.accounts.stage_export(Export(user_id=user.id))
        self.repos.session.commit()
        self.queue.enqueue("export_user", user_id=str(user.id), export_id=export.id)
        log.info("export requested user=%s export=%s", user.id, export.id)
        return export.id

    def get_export(self, user_id: uuid.UUID, export_id: str) -> ExportOut:
        export = self.repos.accounts.get_export(user_id, export_id)
        if export is None:
            raise NotFound("Export not found")
        now = datetime.now(UTC)
        status, url = export.status, None
        expires = as_utc(export.expires_at) if export.expires_at else None
        if status == "ready" and expires is not None and expires <= now:
            status = "expired"
        if status == "ready" and export.storage_key and expires is not None:
            ttl = int(min(settings.export_link_ttl_s, (expires - now).total_seconds()))
            url = signing.sign(
                export.storage_key,
                ttl,
                filename=f"job-copilot-export-{export.id[:8]}.zip",
                decrypt=True,
            )
        return ExportOut(
            export_id=export.id,
            status=status,
            created_at=export.created_at,
            expires_at=expires,
            download_url=url,
        )

    # --- delete --------------------------------------------------------------
    def delete(self, user: User, claims: dict[str, Any]) -> None:
        signed_in = claims.get("auth_time") or claims.get("iat")
        if signed_in is None or signing.now() - signed_in > settings.reauth_window_s:
            raise Unauthorized(
                "Sign in again to delete your account", code="reauth_required"
            )
        now = datetime.now(UTC)
        user.status = "deleting"
        user.sessions_valid_after = now  # every token, including this one, is done
        self.repos.session.commit()
        cancelled = 0
        for run in self.repos.accounts.runs_in(user.id, RUN_ACTIVE):
            try:
                transition(self.repos, run, "cancelled", reason="account_deleted")
                cancelled += 1
            except IllegalTransition:
                self.repos.session.rollback()  # it moved on by itself
        try:
            self.idp.revoke_sessions(user.auth0_sub)
        except Exception as e:  # noqa: BLE001
            log.error(
                "idp session revoke failed user=%s error=%s", user.id, type(e).__name__
            )
        self.queue.enqueue("delete_user", user_id=str(user.id))
        log.info(
            "account deletion started user=%s cancelled_runs=%d", user.id, cancelled
        )


def export_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(days=settings.export_ttl_days)
