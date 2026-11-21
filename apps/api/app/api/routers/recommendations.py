from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.api.deps_discovery import RecommendationServiceDep
from app.core.exceptions import ErrorBody
from app.schemas.recommendation import DismissIn, RecommendationList, RecommendationOut

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

ERRORS = {
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"},
    409: {"model": ErrorBody, "description": "Conflict; see `code`"},
}


@router.get("", response_model=RecommendationList)
def todays_digest(user: CurrentUser, service: RecommendationServiceDep):
    """Today's recommendations (dismissed ones are hidden)."""
    return RecommendationList(items=service.today(user.id))


@router.post(
    "/{rec_id}/save", response_model=RecommendationOut, responses={404: ERRORS[404]}
)
def save_recommendation(
    rec_id: str, user: CurrentUser, service: RecommendationServiceDep
):
    """Create a job from the catalogue posting (no re-extraction) and score it."""
    return service.save(user.id, rec_id)


@router.post(
    "/{rec_id}/dismiss",
    response_model=RecommendationOut,
    responses={k: ERRORS[k] for k in (404, 409)},
)
def dismiss_recommendation(
    rec_id: str,
    user: CurrentUser,
    service: RecommendationServiceDep,
    body: DismissIn | None = None,
):
    return service.dismiss(user.id, rec_id, body.reason if body else None)
