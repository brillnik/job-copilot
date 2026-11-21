from datetime import datetime

from sqlalchemy import select, update

from app.models.account import DeletionAudit
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_auth0_sub(self, sub: str) -> User | None:
        return self.session.scalar(select(User).where(User.auth0_sub == sub))

    def deleted_at_for_sub(self, sub_hash: str) -> datetime | None:
        row = self.session.scalar(
            select(DeletionAudit.deleted_at)
            .where(DeletionAudit.sub_hash == sub_hash)
            .order_by(DeletionAudit.deleted_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        from app.core.clock import as_utc

        return as_utc(row)

    def cas_preferences_rev(self, user: User, expected: int) -> bool:
        taken = self.session.execute(
            update(User)
            .where(User.id == user.id, User.preferences_rev == expected)
            .values(preferences_rev=expected + 1)
        ).rowcount
        if taken:
            self.session.refresh(user)
        return bool(taken)
