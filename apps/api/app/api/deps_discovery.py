"""Dependencies for recommendations and the extension API.

ExtensionUser accepts ONLY a paired-device token and is used only on /extension/*
routes; normal routes use CurrentUser (Auth0 JWT) and reject device tokens.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ai.embeddings import Embedder
from app.api.deps import Repos, get_embedder
from app.core.exceptions import Unauthorized
from app.models.discovery import ExtensionToken
from app.models.user import User
from app.services.extension import ExtensionService
from app.services.recommendation import RecommendationService, ScoringContext
from app.tasks.jobs import scoring_config
from app.tasks.queue import TaskQueue
from app.tasks.runtime import get_queue

_device_bearer = HTTPBearer(auto_error=False, scheme_name="ExtensionToken")


def get_recommendation_service(
    repos: Repos,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> RecommendationService:
    return RecommendationService(
        repos, queue, ScoringContext(scoring=scoring_config(), embedder=embedder)
    )


RecommendationServiceDep = Annotated[
    RecommendationService, Depends(get_recommendation_service)
]


def get_extension_service(
    repos: Repos, queue: Annotated[TaskQueue, Depends(get_queue)]
) -> ExtensionService:
    return ExtensionService(repos, queue)


ExtensionServiceDep = Annotated[ExtensionService, Depends(get_extension_service)]


def get_extension_auth(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_device_bearer)],
    service: ExtensionServiceDep,
) -> tuple[User, ExtensionToken]:
    if creds is None:
        raise Unauthorized("Missing device token", code="invalid_token")
    return service.authenticate(creds.credentials)


def get_extension_user(
    auth: Annotated[tuple[User, ExtensionToken], Depends(get_extension_auth)],
) -> User:
    return auth[0]


ExtensionUser = Annotated[User, Depends(get_extension_user)]
