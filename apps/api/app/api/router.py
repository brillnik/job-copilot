from fastapi import APIRouter

from app.api.routers import events, health, jobs, profile, resumes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(jobs.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
