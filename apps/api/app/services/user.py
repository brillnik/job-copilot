import logging
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.clock import as_utc
from app.core.config import settings
from app.core.exceptions import Forbidden, Unauthorized
from app.core.privacy import hash_sub
from app.models.user import User
from app.repositories.manager import RepositoryManager

log = logging.getLogger(__name__)


class UserService:
    def __init__(self, repos: RepositoryManager) -> None:
        self.repos = repos

    def _refuse_stale_token_of_deleted_account(self, sub: str, iat: int | None) -> None:
        """A token issued before the account was erased must not recreate it."""
        erased = self.repos.users.deleted_at_for_sub(hash_sub(sub))
        if erased is not None and (iat is None or iat <= erased.timestamp()):
            log.info("token of a deleted account refused")
            raise Unauthorized("This account was deleted", code="account_deleted")

    @staticmethod
    def _check_account_state(user: User, iat: int | None) -> None:
        cutoff = user.sessions_valid_after
        if cutoff is not None and (
            iat is None or iat <= int(as_utc(cutoff).timestamp())
        ):
            log.info("revoked session refused user=%s", user.id)
            raise Unauthorized("This session was signed out", code="session_revoked")
        if user.status == "deleting":
            raise Forbidden("This account is being deleted", code="account_deleting")

    def get_or_create(self, claims: dict[str, Any]) -> User:
        """Find the user for a validated token, creating it on first sight."""
        sub = claims["sub"]
        iat = claims.get("iat")
        email = claims.get(settings.auth0_email_claim)
        name = claims.get(settings.auth0_name_claim)

        user = self.repos.users.get_by_auth0_sub(sub)
        if user is None:
            self._refuse_stale_token_of_deleted_account(sub, iat)
            try:
                user = self.repos.users.add(User(auth0_sub=sub, email=email, name=name))
                log.info("user created id=%s", user.id)
                return user
            except IntegrityError:
                # Lost a race with a concurrent first request for the same user.
                log.info("user create raced with another request; reloading")
                self.repos.session.rollback()
                user = self.repos.users.get_by_auth0_sub(sub)
                if user is None:
                    log.error("user missing after create conflict")
                    raise

        self._check_account_state(user, iat)
        # Only overwrite with values the token actually carries.
        changed = []
        for field, value in (("email", email), ("name", name)):
            if value and getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        if not changed:
            log.debug("user resolved id=%s", user.id)
            return user
        log.info("user profile fields updated id=%s fields=%s", user.id, changed)
        return self.repos.users.update(user)
