from fastapi import APIRouter, status

from app.api.deps import AccountServiceDep, Claims, CurrentUser
from app.core.exceptions import ErrorBody
from app.schemas.account import (
    Consent,
    ConsentIn,
    DeleteIn,
    DeleteOut,
    ExportOut,
    ExportRef,
    MeOut,
)

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, service: AccountServiceDep):
    return service.me(user)


@router.post("/me/consent", response_model=Consent, status_code=status.HTTP_201_CREATED)
def consent(body: ConsentIn, user: CurrentUser, service: AccountServiceDep):
    """Append to the consent log (rows are never updated)."""
    return service.consent(user, body.policy_version)


@router.post(
    "/auth/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out everywhere",
)
def logout_all(user: CurrentUser, service: AccountServiceDep):
    """Every token issued up to now stops working, including the caller's."""
    service.logout_all(user)


@router.post(
    "/me/export", response_model=ExportRef, status_code=status.HTTP_202_ACCEPTED
)
def request_export(user: CurrentUser, service: AccountServiceDep):
    """Build an encrypted zip of all your data. A request while one is pending
    returns the pending export's id."""
    return ExportRef(export_id=service.request_export(user))


@router.get(
    "/me/export/{export_id}",
    response_model=ExportOut,
    responses={404: {"model": ErrorBody, "description": "Not found"}},
)
def get_export(export_id: str, user: CurrentUser, service: AccountServiceDep):
    """Status, and a signed download URL (valid 24 h) once ready. Exports expire
    after 7 days."""
    return service.get_export(user.id, export_id)


@router.delete(
    "/me",
    response_model=DeleteOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorBody, "description": "`reauth_required`: sign in again"},
        422: {"model": ErrorBody, "description": '`confirm` must be "DELETE"'},
    },
)
def delete_me(
    body: DeleteIn, user: CurrentUser, claims: Claims, service: AccountServiceDep
):
    """Starts erasure: sessions end now, active runs are cancelled, and a background
    task removes every row and file within 24 h."""
    service.delete(user, claims)
    return DeleteOut()
