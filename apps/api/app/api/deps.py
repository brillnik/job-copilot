from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import Claims
from app.db.session import get_db
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.services.resume import ResumeService
from app.services.user import UserService
from app.storage.base import Storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage

DbSession = Annotated[Session, Depends(get_db)]


def get_repos(db: DbSession) -> RepositoryManager:
    return RepositoryManager(db)


def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url or None,
            access_key=settings.s3_access_key or None,
            secret_key=settings.s3_secret_key or None,
            region=settings.s3_region,
        )
    return LocalStorage(settings.upload_dir)


Repos = Annotated[RepositoryManager, Depends(get_repos)]


def get_resume_service(
    repos: Repos, storage: Annotated[Storage, Depends(get_storage)]
) -> ResumeService:
    return ResumeService(repos, storage, settings.max_resume_bytes)


ResumeServiceDep = Annotated[ResumeService, Depends(get_resume_service)]


def get_current_user(claims: Claims, repos: Repos) -> User:
    return UserService(repos).get_or_create(claims)


CurrentUser = Annotated[User, Depends(get_current_user)]
