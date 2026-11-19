import logging
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.user import User
from app.repositories.manager import RepositoryManager

log = logging.getLogger(__name__)


class UserService:
    def __init__(self, repos: RepositoryManager) -> None:
        self.repos = repos

    def get_or_create(self, claims: dict[str, Any]) -> User:
        """Find the user for a validated token, creating it on first sight."""
        sub = claims["sub"]
        email = claims.get(settings.auth0_email_claim)
        name = claims.get(settings.auth0_name_claim)

        user = self.repos.users.get_by_auth0_sub(sub)
        if user is None:
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
