from sqlalchemy.orm import Session

from app.repositories.resume import ResumeRepository
from app.repositories.user import UserRepository


class RepositoryManager:
    """Single entry point to all repositories, sharing one Session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.resumes = ResumeRepository(session)
        self.users = UserRepository(session)
