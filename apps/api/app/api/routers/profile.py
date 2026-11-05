from fastapi import APIRouter, UploadFile, status

from app.api.deps import CurrentUser, ProfileServiceDep
from app.schemas.profile import (
    BulletSearch,
    BulletSearchOut,
    ProfileData,
    ProfileOut,
)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=ProfileOut)
def upload_resume(file: UploadFile, user: CurrentUser, service: ProfileServiceDep):
    """Upload a resume (PDF/DOCX); Claude extracts it into the draft profile."""
    return service.upload(user.id, file.filename or "", file.file)


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, service: ProfileServiceDep):
    """The latest approved profile."""
    return service.get_approved(user.id)


@router.get("/draft", response_model=ProfileOut)
def get_draft(user: CurrentUser, service: ProfileServiceDep):
    return service.get_draft(user.id)


@router.put("/draft", response_model=ProfileOut)
def put_draft(body: ProfileData, user: CurrentUser, service: ProfileServiceDep):
    """Replace the draft (created if absent). Keep bullet ids to preserve citations."""
    return service.save_draft(user.id, body)


@router.post("/bullets", response_model=BulletSearchOut)
def search_bullets(body: BulletSearch, user: CurrentUser, service: ProfileServiceDep):
    """Retrieve the approved profile's bullets best matching a JD's must-haves."""
    return service.search_bullets(user.id, body)


@router.post("/approve", response_model=ProfileOut)
def approve(user: CurrentUser, service: ProfileServiceDep):
    """Promote the draft to a new approved version and index its bullets."""
    return service.approve(user.id)
