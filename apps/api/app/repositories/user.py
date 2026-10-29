from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_auth0_sub(self, sub: str) -> User | None:
        return self.session.scalar(select(User).where(User.auth0_sub == sub))
