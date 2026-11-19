from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, JobServiceDep
from app.core.exceptions import ErrorBody
from app.schemas.job import (
    ImageOut,
    JobAdd,
    JobAddOut,
    JobDetail,
    JobList,
    JobPatch,
    JobStatus,
    TailorIn,
    TailorOut,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

ERRORS = {
    404: {"model": ErrorBody, "description": "Not found (also for other users' ids)"},
    409: {"model": ErrorBody, "description": "Conflict; see `code`"},
    422: {"model": ErrorBody, "description": "Validation error"},
    429: {"model": ErrorBody, "description": "Rate limit or daily cap"},
}


@router.post(
    "/images",
    status_code=status.HTTP_201_CREATED,
    response_model=ImageOut,
    responses={k: ERRORS[k] for k in (422,)},
)
def upload_image(file: UploadFile, user: CurrentUser, service: JobServiceDep):
    """Upload a PNG/JPEG screenshot to use as `image_id` in POST /jobs."""
    return ImageOut(image_id=service.upload_image(user.id, file.file).id)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAddOut,
    responses={
        200: {"model": JobAddOut, "description": "Duplicate of an existing job"},
        **{k: ERRORS[k] for k in (404, 422, 429)},
    },
)
def add_job(
    body: JobAdd, response: Response, user: CurrentUser, service: JobServiceDep
):
    """Add a job from a URL, pasted text or screenshot; extraction runs in the background."""
    result, created = service.add(user.id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("", response_model=JobList, responses={422: ERRORS[422]})
def list_jobs(
    user: CurrentUser,
    service: JobServiceDep,
    status: JobStatus | None = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    city: str | None = None,
    q: str | None = None,
    sort: Literal["score", "created_at"] = "created_at",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return service.list(
        user.id,
        status=status,
        min_score=min_score,
        city=city,
        q=q,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{job_id}", response_model=JobDetail, responses={404: ERRORS[404]})
def get_job(job_id: str, user: CurrentUser, service: JobServiceDep):
    return service.detail(user.id, job_id)


@router.patch(
    "/{job_id}",
    response_model=JobDetail,
    responses={k: ERRORS[k] for k in (404, 409, 422)},
)
def patch_job(job_id: str, body: JobPatch, user: CurrentUser, service: JobServiceDep):
    """Send exactly one of: `text`, `archived`, `max_pages_override`."""
    return service.patch(user.id, job_id, body)


@router.post(
    "/{job_id}/tailor",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TailorOut,
    responses={k: ERRORS[k] for k in (404, 409, 429)},
)
def tailor_job(
    job_id: str,
    user: CurrentUser,
    service: JobServiceDep,
    body: TailorIn | None = None,
):
    """Start a tailoring run. 409 codes: jd_not_ready, red_flags, no_profile,
    profile_indexing, run_in_progress. 429 code: daily_cap."""
    return TailorOut(run_id=service.tailor(user.id, job_id, body or TailorIn()))
