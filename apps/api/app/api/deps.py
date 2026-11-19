from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder, FastEmbedEmbedder, HashingEmbedder
from app.ai.extractor import ProfileExtractor
from app.ai.factory import build_profile_extractor
from app.core.config import settings
from app.core.security import Claims
from app.db.session import get_db
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.services.job import JobService
from app.services.profile import ProfileService
from app.services.resume import ResumeService
from app.services.user import UserService
from app.storage.base import Storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from app.tasks.queue import TaskQueue
from app.tasks.runtime import get_queue

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


def get_extractor() -> ProfileExtractor:
    return build_profile_extractor()


def get_embedder() -> Embedder:
    if settings.embedding_backend == "hashing":
        return HashingEmbedder()
    return FastEmbedEmbedder(settings.embedding_model)


def get_profile_service(
    repos: Repos,
    resumes: ResumeServiceDep,
    extractor: Annotated[ProfileExtractor, Depends(get_extractor)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> ProfileService:
    return ProfileService(repos, resumes, extractor, embedder, queue)


ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]


def get_job_service(
    repos: Repos,
    storage: Annotated[Storage, Depends(get_storage)],
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> JobService:
    return JobService(repos, queue, storage)


JobServiceDep = Annotated[JobService, Depends(get_job_service)]


def get_current_user(claims: Claims, repos: Repos) -> User:
    return UserService(repos).get_or_create(claims)


CurrentUser = Annotated[User, Depends(get_current_user)]
