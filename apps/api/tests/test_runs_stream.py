import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.security import token_claims
from app.main import app
from app.models.run import RunEvent
from app.services import run_stream
from tests.jobs_helpers import make_user
from tests.runs_helpers import run_ready

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def parse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if "data" in fields:
            events.append(
                (int(fields["id"]), fields["event"], json.loads(fields["data"]))
            )
    return events


def finished_run(db, tmp_path, user):
    run = run_ready(db, tmp_path, user, status="queued")
    client.post(f"/runs/{run.id}/cancel")  # terminal: the stream will close
    return run


def test_replays_every_event_then_closes_on_terminal_status(db_session, tmp_path, user):
    run = finished_run(db_session, tmp_path, user)
    r = client.get(f"/runs/{run.id}/events")
    assert r.status_code == 200 and r.headers["content-type"].startswith(
        "text/event-stream"
    )
    events = parse(r.text)
    assert [e[0] for e in events] == [1, 2]
    assert [(e[1], e[2]["payload"]["status"]) for e in events] == [
        ("status", "queued"),
        ("status", "cancelled"),
    ]


def test_resumes_after_last_event_id(db_session, tmp_path, user):
    run = finished_run(db_session, tmp_path, user)
    assert [
        e[0]
        for e in parse(
            client.get(f"/runs/{run.id}/events", headers={"Last-Event-ID": "1"}).text
        )
    ] == [2]
    assert (
        parse(client.get(f"/runs/{run.id}/events", headers={"Last-Event-ID": "2"}).text)
        == []
    )
    # garbage falls back to a full replay
    assert (
        len(
            parse(
                client.get(
                    f"/runs/{run.id}/events", headers={"Last-Event-ID": "x"}
                ).text
            )
        )
        == 2
    )


def test_other_users_stream_is_404_and_leaks_nothing(db_session, tmp_path, user):
    run = finished_run(db_session, tmp_path, user)
    make_user(db_session, "auth0|B")
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|B"}
    r = client.get(f"/runs/{run.id}/events")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert "status" not in r.text.replace("not_found", "")


def test_the_log_is_filtered_by_owner_in_the_query_itself(db_session, tmp_path, user):
    from app.repositories.manager import RepositoryManager

    run = finished_run(db_session, tmp_path, user)
    other = make_user(db_session, "auth0|B")
    assert RepositoryManager(db_session).runs.events_after(other.id, run.id, 0) == []
    assert db_session.query(RunEvent).count() == 2


# --- the stream loop itself (heartbeat, live events) -------------------------
def collect(fetch, after=0, limit=None, poll=0.005, heartbeat=0.02):
    async def go():
        out = []

        async def never():
            return False

        async for chunk in run_stream.stream(
            fetch, after, poll_s=poll, heartbeat_s=heartbeat, disconnected=never
        ):
            out.append(chunk)
            if limit and len(out) >= limit:
                break
        return out

    return asyncio.run(go())


def test_heartbeat_is_sent_while_idle():
    async def fetch(cursor):
        return run_stream.Batch(events=[], status="in_review")

    chunks = collect(fetch, limit=3)
    assert chunks == [": heartbeat\n\n"] * 3


def test_default_heartbeat_interval_is_fifteen_seconds():
    from app.core.config import settings

    assert settings.sse_heartbeat_s == 15


def test_follows_live_events_and_closes_after_the_terminal_one():
    script = [
        run_stream.Batch([], "running"),
        run_stream.Batch([(1, "status", {"status": "running"}, "t")], "running"),
        run_stream.Batch([], "running"),
        run_stream.Batch([(2, "status", {"status": "in_review"}, "t")], "in_review"),
        run_stream.Batch([(3, "status", {"status": "approved"}, "t")], "approved"),
        run_stream.Batch([], "approved"),
    ]
    cursors = []

    async def fetch(cursor):
        cursors.append(cursor)
        return script.pop(0)

    chunks = collect(fetch, heartbeat=100)
    assert [c.split("\n")[0] for c in chunks] == ["id: 1", "id: 2", "id: 3"]
    assert cursors[-1] == 3 and script == []  # ended without polling forever


def test_stops_when_the_client_disconnects():
    async def fetch(cursor):
        return run_stream.Batch([], "in_review")

    async def go():
        async def gone():
            return True

        return [
            c
            async for c in run_stream.stream(
                fetch, 0, poll_s=0.001, heartbeat_s=0.001, disconnected=gone
            )
        ]

    assert asyncio.run(go()) == []
