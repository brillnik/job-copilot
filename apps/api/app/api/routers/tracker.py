from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.api.deps import CurrentUser, TrackerServiceDep
from app.api.etag import etag, parse_if_match
from app.core.exceptions import ErrorBody
from app.schemas.tracker import Board, CardDetail, TrackerAdd, TrackerPatch

router = APIRouter(prefix="/tracker", tags=["tracker"])

ERRORS = {
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"},
    409: {"model": ErrorBody, "description": "Conflict; see `code`"},
    422: {"model": ErrorBody, "description": "Validation error"},
}


@router.get("", response_model=Board)
def board(user: CurrentUser, service: TrackerServiceDep):
    return service.board(user.id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CardDetail,
    responses={k: ERRORS[k] for k in (404, 409, 422)},
)
def add_card(body: TrackerAdd, user: CurrentUser, service: TrackerServiceDep):
    """Add a job by hand (e.g. applied without tailoring). 409 `already_tracked`."""
    return service.add(user.id, body)


@router.patch(
    "/{card_id}",
    response_model=CardDetail,
    responses={k: ERRORS[k] for k in (404, 409, 422)},
)
def patch_card(
    card_id: str,
    body: TrackerPatch,
    response: Response,
    user: CurrentUser,
    service: TrackerServiceDep,
    if_match: Annotated[str | None, Header()] = None,
):
    """Move, reorder or annotate. `position` is the 0-based index in the target column.
    Send the card's `rev` as `If-Match`; a stale one gives 409 `stale_write`."""
    card = service.patch(user.id, card_id, body, parse_if_match(if_match))
    response.headers["ETag"] = etag(card.rev)
    return card


@router.delete(
    "/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: ERRORS[404]},
)
def delete_card(card_id: str, user: CurrentUser, service: TrackerServiceDep):
    service.delete(user.id, card_id)
