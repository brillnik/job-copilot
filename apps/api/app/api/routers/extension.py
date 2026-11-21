from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import ApplicationServiceDep, CurrentUser
from app.api.deps_discovery import ExtensionServiceDep, ExtensionUser
from app.core.exceptions import ErrorBody
from app.schemas.application import ApplicationOut
from app.schemas.extension import (
    ApplyResultIn,
    ClipIn,
    PairCodeOut,
    PairIn,
    PairOut,
    TokenOut,
)
from app.schemas.job import JobAddOut

router = APIRouter(prefix="/extension", tags=["extension"])


@router.post("/pair-code", response_model=PairCodeOut)
def create_pair_code(user: CurrentUser, service: ExtensionServiceDep):
    """One-time code (valid 10 minutes) the user types into the extension."""
    return service.new_code(user.id)


@router.post(
    "/pair",
    response_model=PairOut,
    responses={401: {"model": ErrorBody}, 429: {"model": ErrorBody}},
)
def pair(body: PairIn, request: Request, service: ExtensionServiceDep):
    """Exchange a pairing code for a device token (shown once). No other auth."""
    client = request.client.host if request.client else "unknown"
    return service.pair(body.code, body.device_name, client)


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(user: CurrentUser, service: ExtensionServiceDep):
    return [
        TokenOut.model_validate(t, from_attributes=True)
        for t in service.repos.extension.tokens_for_user(user.id)
    ]


@router.delete(
    "/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorBody}},
)
def revoke_token(token_id: str, user: CurrentUser, service: ExtensionServiceDep):
    service.revoke(user.id, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clip",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAddOut,
    responses={
        200: {"model": JobAddOut, "description": "Duplicate of an existing job"},
        401: {"model": ErrorBody},
        429: {"model": ErrorBody},
    },
)
def clip(
    body: ClipIn, response: Response, user: ExtensionUser, service: ExtensionServiceDep
):
    """Save the posting text the extension read in the user's browser. The URL is
    kept as a reference; the server never fetches it. Device token only."""
    out, created = service.clip(user.id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    return out


@router.get("/apply-queue", response_model=list[ApplicationOut])
def apply_queue(user: ExtensionUser, apps: ApplicationServiceDep):
    """Approved applications for sites the user opted in to, within today's caps.
    Device token only."""
    return apps.extension_queue(user.id)


@router.get(
    "/apply-plan/{application_id}",
    responses={
        404: {"model": ErrorBody},
        409: {"model": ErrorBody},
        429: {"model": ErrorBody},
    },
)
def apply_plan(
    application_id: str,
    user: ExtensionUser,
    apps: ApplicationServiceDep,
    required: Annotated[list[str] | None, Query(max_length=30)] = None,
):
    """Signed PDF URL, contact fields, mapped answers and the required fields with no
    value (the extension must skip the application if that list is not empty). Takes
    the cap slot and marks the application running; repeating the call is harmless."""
    return apps.extension_plan(user.id, application_id, required or [])


@router.post(
    "/apply-result/{application_id}",
    response_model=ApplicationOut,
    responses={
        404: {"model": ErrorBody},
        409: {"model": ErrorBody},
        422: {"model": ErrorBody},
    },
)
def apply_result(
    application_id: str,
    body: ApplyResultIn,
    user: ExtensionUser,
    apps: ApplicationServiceDep,
):
    """Report submitted / skipped / error. Same post-submit handling as the worker;
    repeated blocks pause the site."""
    return apps.extension_result(
        user.id, application_id, body.status, body.reason, body.screenshot
    )
