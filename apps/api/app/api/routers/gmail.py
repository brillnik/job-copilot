from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, GmailServiceDep
from app.core.config import settings
from app.core.exceptions import ErrorBody
from app.schemas.gmail import (
    ConnectedOut,
    ConnectOut,
    GmailStatus,
    PushEnvelope,
    Suggestion,
)

router = APIRouter(prefix="/integrations/gmail", tags=["gmail"])

ERRORS = {
    403: {
        "model": ErrorBody,
        "description": "Feature off for this user, or bad push token",
    },
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"},
    409: {"model": ErrorBody, "description": "Already resolved"},
}


@router.get("", response_model=GmailStatus)
def gmail_status(user: CurrentUser, service: GmailServiceDep):
    """Connection state. `enabled: false` means the feature is off for this user."""
    return service.status(user.id)


@router.get("/connect", response_model=ConnectOut, responses={403: ERRORS[403]})
def connect(user: CurrentUser, service: GmailServiceDep):
    """The Google consent URL (gmail.readonly, offline). Open it in the browser."""
    return service.connect_url(user.id)


@router.get("/callback", response_model=ConnectedOut, responses={403: ERRORS[403]})
def callback(
    service: GmailServiceDep,
    state: str,
    code: str | None = None,
    error: str | None = None,
):
    """Google redirects here (no bearer token): the signed `state` names the user."""
    out = service.callback(code, state, error)
    if settings.gmail_post_connect_url:
        return RedirectResponse(settings.gmail_post_connect_url, status_code=303)
    return out


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses={403: ERRORS[403]})
def disconnect(user: CurrentUser, service: GmailServiceDep):
    """Revoke at Google, then delete the connection and every email_event."""
    service.disconnect(user.id)


@router.get(
    "/suggestions", response_model=list[Suggestion], responses={403: ERRORS[403]}
)
def suggestions(user: CurrentUser, service: GmailServiceDep):
    return service.suggestions(user.id)


@router.post(
    "/suggestions/{suggestion_id}/accept",
    response_model=Suggestion,
    responses={k: ERRORS[k] for k in (403, 404, 409)},
)
def accept(suggestion_id: str, user: CurrentUser, service: GmailServiceDep):
    return service.accept(user.id, suggestion_id)


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=Suggestion,
    responses={k: ERRORS[k] for k in (403, 404, 409)},
)
def dismiss(suggestion_id: str, user: CurrentUser, service: GmailServiceDep):
    return service.dismiss(user.id, suggestion_id)


@router.post(
    "/push", status_code=status.HTTP_204_NO_CONTENT, responses={403: ERRORS[403]}
)
def push(
    body: PushEnvelope,
    service: GmailServiceDep,
    token: Annotated[str | None, Query()] = None,
):
    """Pub/Sub push endpoint. Configure the subscription URL with `?token=<secret>`
    (GMAIL_PUSH_SECRET). Always acks valid pushes, even for unknown mailboxes."""
    service.push(token, body.message.data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
