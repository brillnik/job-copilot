from fastapi import APIRouter, UploadFile, status

from app.api.deps import CurrentUser, ResumeServiceDep
from app.schemas.resume import ResumeOut

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ResumeOut)
def upload_resume(file: UploadFile, user: CurrentUser, service: ResumeServiceDep):
    return service.upload(user.id, file.filename or "", file.file)
