from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, StreamingResponse

from app.api.deps import (
    ApplicationServiceDep,
    CurrentUser,
    Repos,
    RunServiceDep,
    SessionFactory,
)
from app.api.etag import etag, parse_if_match
from app.core.config import settings
from app.core.exceptions import ErrorBody, NotFound
from app.repositories.manager import RepositoryManager
from app.schemas.application import ApplicationOut
from app.schemas.job import TailorOut
from app.schemas.run import (
    AnswerIn,
    ApproveOut,
    DraftEdit,
    DraftEditOut,
    RegenerateIn,
    RejectIn,
    RunDetail,
    RunList,
    RunRef,
    RunStatus,
)
from app.services import run_stream

router = APIRouter(prefix="/runs", tags=["runs"])

ERRORS = {
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"},
    409: {"model": ErrorBody, "description": "Conflict; see `code`"},
    422: {"model": ErrorBody, "description": "Validation error"},
    429: {"model": ErrorBody, "description": "Daily cap"},
}


def _errs(*codes: int) -> dict:
    return {c: ERRORS[c] for c in codes}


@router.get("", response_model=RunList, responses=_errs(422))
def list_runs(
    user: CurrentUser,
    service: RunServiceDep,
    status: RunStatus | None = None,
    job_id: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return service.list_runs(
        user.id, status=status, job_id=job_id, cursor=cursor, limit=limit
    )


@router.get("/{run_id}", response_model=RunDetail, responses=_errs(404))
def get_run(run_id: str, response: Response, user: CurrentUser, service: RunServiceDep):
    """The run with its latest draft and per-bullet diff. `ETag` is the draft revision."""
    out = service.detail(user.id, run_id)
    if out.draft_rev is not None:
        response.headers["ETag"] = etag(out.draft_rev)
    return out


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE stream"},
        **_errs(404),
    },
)
async def run_events(
    run_id: str,
    request: Request,
    user: CurrentUser,
    repos: Repos,
    factory: SessionFactory,
    last_event_id: Annotated[str | None, Header()] = None,
):
    """Replays events after `Last-Event-ID`, then streams live until the run ends
    (approved, rejected, needs_attention, cancelled). A comment heartbeat is sent
    every 15 s."""
    if repos.runs.get_for_user(user.id, run_id) is None:
        raise NotFound("Run not found")
    try:
        after = max(0, int(last_event_id or 0))
    except ValueError:
        after = 0
    user_id = user.id

    def read(cursor: int) -> run_stream.Batch:
        with factory() as session:
            r = RepositoryManager(session)
            rows = r.runs.events_after(user_id, run_id, cursor)
            return run_stream.Batch(
                events=[(e.seq, e.type, e.payload, e.ts.isoformat()) for e in rows],
                status=r.runs.status_of(user_id, run_id),
            )

    async def fetch(cursor: int) -> run_stream.Batch:
        return await run_in_threadpool(read, cursor)

    body = run_stream.stream(
        fetch,
        after,
        poll_s=settings.sse_poll_s,
        heartbeat_s=settings.sse_heartbeat_s,
        disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{run_id}/answer",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunRef,
    responses=_errs(404, 409, 422),
)
def answer(run_id: str, body: AnswerIn, user: CurrentUser, service: RunServiceDep):
    """Answer the run's skill questions and resume it. 409 unless waiting_for_user."""
    return service.answer(user.id, run_id, body)


@router.put(
    "/{run_id}/draft",
    response_model=DraftEditOut,
    responses=_errs(404, 409, 422),
)
def edit_draft(
    run_id: str,
    body: DraftEdit,
    response: Response,
    user: CurrentUser,
    service: RunServiceDep,
    if_match: Annotated[str | None, Header()] = None,
):
    """Edit the draft while in_review. Every edit is fact-checked against the run's
    profile version; refused edits come back as `blocked` violations. Send the ETag
    as `If-Match`; a stale one gives 409 `stale_write`."""
    out = service.edit_draft(user.id, run_id, body, parse_if_match(if_match))
    if out.run.draft_rev is not None:
        response.headers["ETag"] = etag(out.run.draft_rev)
    return out


@router.post("/{run_id}/approve", response_model=ApproveOut, responses=_errs(404, 409))
def approve(run_id: str, user: CurrentUser, service: RunServiceDep):
    """Idempotent: approving an approved run returns the same approval."""
    return service.approve(user.id, run_id)


@router.post(
    "/{run_id}/apply",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApplicationOut,
    responses=_errs(404, 409, 422),
)
def apply_run(run_id: str, user: CurrentUser, apps: ApplicationServiceDep):
    """Manual apply with the approved resume. One application per job: repeating the
    call returns the existing one. 409 unless the run is approved (or the site is not
    opted in / paused / switched off)."""
    return apps.out(apps.create_for_run(user.id, run_id, mode="manual"))


@router.post("/{run_id}/reject", response_model=RunRef, responses=_errs(404, 409, 422))
def reject(run_id: str, body: RejectIn, user: CurrentUser, service: RunServiceDep):
    return service.reject(user.id, run_id, body)


@router.post(
    "/{run_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TailorOut,
    responses=_errs(404, 409, 422, 429),
)
def regenerate(
    run_id: str,
    user: CurrentUser,
    service: RunServiceDep,
    body: RegenerateIn | None = None,
):
    """New run for the same job on the CURRENT approved profile. Same 409/429 codes as
    POST /jobs/{id}/tailor."""
    return TailorOut(run_id=service.regenerate(user.id, run_id, body or RegenerateIn()))


@router.post("/{run_id}/cancel", response_model=RunRef, responses=_errs(404, 409))
def cancel(run_id: str, user: CurrentUser, service: RunServiceDep):
    """From queued, running or waiting_for_user. Does not count against the daily cap."""
    return service.cancel(user.id, run_id)


@router.get(
    "/{run_id}/pdf",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {"description": "Redirect to a signed URL valid for 5 minutes"},
        **_errs(404),
    },
)
def pdf(
    run_id: str,
    user: CurrentUser,
    service: RunServiceDep,
    draft: Literal["latest", "approved"] = "latest",
):
    return RedirectResponse(service.pdf_url(user.id, run_id, draft), status_code=302)
