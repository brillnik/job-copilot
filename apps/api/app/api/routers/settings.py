from typing import Annotated

from fastapi import APIRouter, Header, Response

from app.api.deps import CurrentUser, SettingsServiceDep
from app.api.etag import etag, parse_if_match
from app.core.exceptions import ErrorBody
from app.schemas.account import Preferences, SettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings(response: Response, user: CurrentUser, service: SettingsServiceDep):
    out = service.get(user.id)
    response.headers["ETag"] = etag(out.rev)
    return out


@router.put(
    "",
    response_model=SettingsOut,
    responses={
        409: {"model": ErrorBody, "description": "Stale write (`stale_write`)"},
        422: {
            "model": ErrorBody,
            "description": "Validation error; unknown fields too",
        },
    },
)
def put_settings(
    body: Preferences,
    response: Response,
    user: CurrentUser,
    service: SettingsServiceDep,
    if_match: Annotated[str | None, Header()] = None,
):
    """Replace all preferences. Changing cities, expected CTC or target roles
    re-scores open jobs in the background. `daily_cap` applies from the next run."""
    out = service.put(user.id, body, parse_if_match(if_match))
    response.headers["ETag"] = etag(out.rev)
    return out
