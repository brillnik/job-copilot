from fastapi import APIRouter

from app.api.deps import AutopilotServiceDep, CurrentUser
from app.core.exceptions import ErrorBody
from app.schemas.autopilot import AutopilotOut, AutopilotPut, DigestOut

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.get("", response_model=AutopilotOut)
def get_autopilot(user: CurrentUser, service: AutopilotServiceDep):
    """Autopilot settings. Off by default."""
    return service.get(user.id)


@router.put("", response_model=AutopilotOut, responses={422: {"model": ErrorBody}})
def put_autopilot(body: AutopilotPut, user: CurrentUser, service: AutopilotServiceDep):
    """Enabling needs `acknowledgement_version` equal to the current policy version
    (422 acknowledgement_required otherwise); each of wellfound / naukri / hiring_cafe
    needs its own acknowledgement."""
    return service.put(user.id, body)


@router.get("/digest", response_model=DigestOut, responses={422: {"model": ErrorBody}})
def digest(user: CurrentUser, service: AutopilotServiceDep, date: str | None = None):
    """Submitted, skipped (reason + direct link) and needs-a-person items for a day."""
    return service.digest(user.id, date)
