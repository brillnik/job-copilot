from fastapi import APIRouter

from app.api.routers import (
    applications,
    autopilot,
    events,
    extension,
    files,
    gmail,
    health,
    jobs,
    me,
    profile,
    recommendations,
    resumes,
    runs,
    screening,
    settings,
    tracker,
    training,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(files.router)
api_router.include_router(jobs.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
api_router.include_router(runs.router)
api_router.include_router(tracker.router)
api_router.include_router(me.router)
api_router.include_router(settings.router)
api_router.include_router(training.router)
api_router.include_router(gmail.router)
api_router.include_router(screening.router)
api_router.include_router(recommendations.router)
api_router.include_router(extension.router)
api_router.include_router(applications.router)
api_router.include_router(autopilot.router)
