from fastapi import APIRouter, status

from app.api.deps import CurrentUser, ScreeningServiceDep
from app.core.exceptions import ErrorBody
from app.schemas.screening import (
    ScreeningAnswerList,
    ScreeningAnswerOut,
    ScreeningAnswerPut,
)

router = APIRouter(prefix="/screening-answers", tags=["screening"])

NOT_FOUND = {
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"}
}


@router.get("", response_model=ScreeningAnswerList)
def list_answers(user: CurrentUser, service: ScreeningServiceDep):
    return service.list_answers(user.id)


@router.put("/{answer_id}", response_model=ScreeningAnswerOut, responses=NOT_FOUND)
def put_answer(
    answer_id: str,
    body: ScreeningAnswerPut,
    user: CurrentUser,
    service: ScreeningServiceDep,
):
    """Edit a saved answer (it then counts as the user's own)."""
    return service.update(user.id, answer_id, body)


@router.delete(
    "/{answer_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND
)
def delete_answer(answer_id: str, user: CurrentUser, service: ScreeningServiceDep):
    service.delete(user.id, answer_id)
