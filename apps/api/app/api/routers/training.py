from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, Repos
from app.schemas.training import TrainingConsentIn, TrainingConsentOut
from app.services.training import TrainingService

router = APIRouter(tags=["training"])


def get_training_service(repos: Repos) -> TrainingService:
    return TrainingService(repos)


TrainingServiceDep = Annotated[TrainingService, Depends(get_training_service)]


@router.get("/me/training-consent", response_model=TrainingConsentOut)
def get_training_consent(user: CurrentUser, service: TrainingServiceDep):
    """Current state (the latest log row); `enabled: false` if never set."""
    return service.get(user.id)


@router.put("/me/training-consent", response_model=TrainingConsentOut)
def put_training_consent(
    body: TrainingConsentIn, user: CurrentUser, service: TrainingServiceDep
):
    """Opt in or out of having your (anonymised) data in model-training snapshots.
    Appends to an immutable log. Revoking excludes you from future snapshots; ones
    already written contain no identifiers and are not rewritten."""
    return service.set(user.id, body.enabled, body.policy_version)
