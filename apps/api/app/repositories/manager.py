from sqlalchemy.orm import Session

from app.repositories.account import AccountRepository
from app.repositories.application import ApplicationRepository
from app.repositories.discovery import (
    CatalogRepository,
    ExtensionRepository,
    RecommendationRepository,
)
from app.repositories.email import EmailRepository
from app.repositories.job import JobRepository
from app.repositories.profile import ProfileRepository
from app.repositories.resume import ResumeRepository
from app.repositories.run import RunRepository
from app.repositories.tracker import TrackerRepository
from app.repositories.user import UserRepository


class RepositoryManager:
    """Single entry point to all repositories, sharing one Session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.accounts = AccountRepository(session)
        self.applications = ApplicationRepository(session)
        self.catalog = CatalogRepository(session)
        self.email = EmailRepository(session)
        self.extension = ExtensionRepository(session)
        self.recommendations = RecommendationRepository(session)
        self.jobs = JobRepository(session)
        self.profiles = ProfileRepository(session)
        self.resumes = ResumeRepository(session)
        self.runs = RunRepository(session)
        self.tracker = TrackerRepository(session)
        self.users = UserRepository(session)
