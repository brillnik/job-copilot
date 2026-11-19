from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, Repos
from app.schemas.job import EventList, EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventList)
def list_events(
    user: CurrentUser,
    repos: Repos,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """The caller's own events with id > `after`. Poll with the returned `last_id`."""
    rows = repos.jobs.events_after(user.id, after, limit)
    return EventList(
        events=[
            EventOut(id=e.id, type=e.type, payload=e.payload, created_at=e.created_at)
            for e in rows
        ],
        last_id=rows[-1].id if rows else after,
    )
