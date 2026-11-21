from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ApplicationServiceDep, CurrentUser
from app.core.exceptions import ErrorBody
from app.schemas.application import (
    ApplicationAnswerIn,
    ApplicationList,
    ApplicationOut,
    ApplicationStatus,
)

router = APIRouter(prefix="/applications", tags=["applications"])
ERR = {404: {"model": ErrorBody}, 409: {"model": ErrorBody}, 422: {"model": ErrorBody}}


@router.get("", response_model=ApplicationList)
def list_applications(
    user: CurrentUser,
    apps: ApplicationServiceDep,
    status: ApplicationStatus | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return apps.list_apps(user.id, status=status, cursor=cursor, limit=limit)


@router.get("/{application_id}", response_model=ApplicationOut, responses=ERR)
def get_application(
    application_id: str, user: CurrentUser, apps: ApplicationServiceDep
):
    return apps.detail(user.id, application_id)


@router.post(
    "/{application_id}/answer",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApplicationOut,
    responses=ERR,
)
def answer_application(
    application_id: str,
    body: ApplicationAnswerIn,
    user: CurrentUser,
    apps: ApplicationServiceDep,
):
    """Answer the required fields a manual application is waiting on and resume it."""
    return apps.answer(user.id, application_id, body)


@router.post("/{application_id}/cancel", response_model=ApplicationOut, responses=ERR)
def cancel_application(
    application_id: str, user: CurrentUser, apps: ApplicationServiceDep
):
    return apps.cancel(user.id, application_id)
