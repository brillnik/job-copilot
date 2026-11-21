from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.clock import week_start
from app.core.security import token_claims
from app.main import app
from app.models.job import Job
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.services.tracker import GAP, TrackerService
from tests.jobs_helpers import make_job, make_user
from tests.runs_helpers import run_ready

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def job(db, user, score=70, company="Acme"):
    return make_job(db, user, company=company, title="Engineer", score=score)


def add(db, user, column="approved", **kw):
    j = job(db, user, **kw)
    r = client.post("/tracker", json={"job_id": j.id, "column": column})
    assert r.status_code == 201, r.text
    return r.json()


def order(column="approved"):
    return [c["id"] for c in client.get("/tracker").json()["columns"][column]]


# --- created by approve ------------------------------------------------------
def test_approve_creates_a_card_and_a_second_approval_reuses_it(
    db_session, tmp_path, user
):
    first = run_ready(db_session, tmp_path, user)
    assert client.post(f"/runs/{first.id}/approve").status_code == 200
    (card,) = client.get("/tracker").json()["columns"]["approved"]
    assert (card["company"], card["title"], card["score"]) == (
        "Globex Corp",
        "Backend Engineer",
        80,
    )

    j = db_session.get(Job, first.job_id)
    second = run_ready(db_session, tmp_path, user, job=j)
    assert client.post(f"/runs/{second.id}/approve").status_code == 200
    cards = client.get("/tracker").json()["columns"]["approved"]
    assert [c["id"] for c in cards] == [card["id"]]
    assert cards[0]["rev"] == card["rev"] + 1  # updated, not duplicated
    assert db_session.query(TrackerCard).count() == 1


def test_approve_does_not_drag_a_progressed_card_backwards(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    j = db_session.get(Job, run.job_id)
    card = client.post("/tracker", json={"job_id": j.id, "column": "interview"}).json()
    assert client.post(f"/runs/{run.id}/approve").status_code == 200
    assert client.get("/tracker").json()["columns"]["interview"][0]["id"] == card["id"]
    assert db_session.query(TrackerCard).count() == 1


# --- add / delete ------------------------------------------------------------
def test_add_manually(db_session, user):
    j = job(db_session, user)
    r = client.post("/tracker", json={"job_id": j.id})
    assert r.status_code == 201
    body = r.json()
    assert body["column"] == "applied" and body["applied_at"] is not None
    assert body["history"][0]["from"] is None and body["history"][0]["to"] == "applied"
    dup = client.post("/tracker", json={"job_id": j.id})
    assert dup.status_code == 409 and dup.json()["code"] == "already_tracked"
    assert dup.json()["details"] == {"card_id": body["id"]}
    assert client.post("/tracker", json={"job_id": "nope"}).status_code == 404
    assert (
        client.post("/tracker", json={"job_id": j.id, "column": "bogus"}).status_code
        == 422
    )


def test_delete_removes_the_card_but_not_the_job(db_session, user):
    card = add(db_session, user)
    assert client.delete(f"/tracker/{card['id']}").status_code == 204
    assert client.get("/tracker").json()["columns"]["approved"] == []
    assert db_session.get(Job, card["job_id"]) is not None
    assert client.delete(f"/tracker/{card['id']}").status_code == 404


# --- moving ------------------------------------------------------------------
def test_moving_to_applied_sets_applied_at_and_history(db_session, user):
    card = add(db_session, user)
    assert card["applied_at"] is None
    r = client.patch(f"/tracker/{card['id']}", json={"column": "applied"})
    assert r.status_code == 200 and r.headers["etag"] == '"2"'
    body = r.json()
    assert body["column"] == "applied"
    assert datetime.fromisoformat(body["applied_at"]) > datetime.now(UTC) - timedelta(
        minutes=1
    )
    assert [(h["from"], h["to"]) for h in body["history"]] == [
        (None, "approved"),
        ("approved", "applied"),
    ]
    # an explicit applied_at wins, and a move without a column change adds no history
    when = "2026-01-05T10:00:00+00:00"
    body = client.patch(
        f"/tracker/{card['id']}", json={"applied_at": when, "notes": "x"}
    ).json()
    assert (
        body["applied_at"].startswith("2026-01-05T10:00") and len(body["history"]) == 2
    )


def test_explicit_applied_at_is_kept_when_moving_to_applied(db_session, user):
    card = add(db_session, user)
    when = "2026-01-05T10:00:00+00:00"
    body = client.patch(
        f"/tracker/{card['id']}", json={"column": "applied", "applied_at": when}
    ).json()
    assert body["applied_at"].startswith("2026-01-05T10:00")


def test_ordering_uses_float_midpoints(db_session, user):
    a, b, c = (add(db_session, user, company=n) for n in "abc")
    assert order() == [a["id"], b["id"], c["id"]]
    moved = client.patch(f"/tracker/{c['id']}", json={"position": 1}).json()
    assert order() == [a["id"], c["id"], b["id"]]
    assert moved["position"] == (a["position"] + b["position"]) / 2
    client.patch(f"/tracker/{b['id']}", json={"position": 0})
    assert order() == [b["id"], a["id"], c["id"]]
    client.patch(f"/tracker/{b['id']}", json={"position": 99})  # past the end = last
    assert order() == [a["id"], c["id"], b["id"]]


def test_a_card_moved_to_another_column_lands_at_the_index(db_session, user):
    a = add(db_session, user, "applied", company="a")
    b = add(db_session, user, "applied", company="b")
    x = add(db_session, user, "approved", company="x")
    client.patch(f"/tracker/{x['id']}", json={"column": "applied", "position": 1})
    assert order("applied") == [a["id"], x["id"], b["id"]] and order("approved") == []
    y = add(db_session, user, "approved", company="y")
    client.patch(f"/tracker/{y['id']}", json={"column": "applied"})  # no index = end
    assert order("applied")[-1] == y["id"]


def test_a_crowded_column_is_rebalanced(db_session, user):
    cards = [add(db_session, user, company=str(i)) for i in range(3)]
    ids = [c["id"] for c in cards]
    # squeeze the first two together so the midpoint has no room
    rows = db_session.scalars(select(TrackerCard).order_by(TrackerCard.position)).all()
    rows[0].position, rows[1].position = 1.0, 1.0 + 1e-9
    db_session.commit()
    client.patch(f"/tracker/{ids[2]}", json={"position": 1})
    assert order() == [ids[0], ids[2], ids[1]]
    positions = [
        r.position
        for r in db_session.scalars(select(TrackerCard).order_by(TrackerCard.position))
    ]
    assert positions == [GAP, 2 * GAP, 3 * GAP]


def test_many_insertions_at_the_same_spot_keep_order_and_distinct_positions(
    db_session, user
):
    first, last = add(db_session, user, company="f"), add(db_session, user, company="l")
    expected = [first["id"], last["id"]]
    for i in range(45):  # halving a 1024 gap 45 times would underflow the 1e-6 floor
        card = add(db_session, user, company=str(i))
        client.patch(f"/tracker/{card['id']}", json={"position": 1})
        expected.insert(1, card["id"])
    assert order() == expected
    pos = [
        r.position
        for r in db_session.scalars(select(TrackerCard).order_by(TrackerCard.position))
    ]
    assert len(set(pos)) == len(pos)


# --- concurrency / validation ------------------------------------------------
def test_stale_write_is_409(db_session, user):
    card = add(db_session, user)
    assert (
        client.patch(
            f"/tracker/{card['id']}", json={"notes": "a"}, headers={"If-Match": '"1"'}
        ).status_code
        == 200
    )
    r = client.patch(
        f"/tracker/{card['id']}", json={"notes": "b"}, headers={"If-Match": '"1"'}
    )
    assert (
        r.status_code == 409
        and r.json()["code"] == "stale_write"
        and r.json()["details"] == {"rev": 2}
    )
    assert (
        client.get("/tracker").json()["columns"]["approved"][0]["notes_preview"] == "a"
    )
    ok = client.patch(
        f"/tracker/{card['id']}", json={"notes": "b"}, headers={"If-Match": '"2"'}
    )
    assert ok.status_code == 200
    assert (
        client.patch(
            f"/tracker/{card['id']}", json={"notes": "b"}, headers={"If-Match": "abc"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"column": "done"},
        {"column": None},
        {"position": -1},
        {"position": 1.5},
        {"bogus": 1},
        {"notes": "x" * 10_001},
    ],
)
def test_patch_validation(db_session, user, body):
    card = add(db_session, user)
    assert client.patch(f"/tracker/{card['id']}", json=body).status_code == 422


def test_notes_preview_is_short(db_session, user):
    card = add(db_session, user)
    client.patch(f"/tracker/{card['id']}", json={"notes": "word " * 100})
    preview = client.get("/tracker").json()["columns"]["approved"][0]["notes_preview"]
    assert len(preview) == 120 and preview.endswith("…")


# --- stats -------------------------------------------------------------------
def test_stats_are_correct(db_session, user):
    now = datetime.now(UTC)
    this_week = week_start() + timedelta(seconds=1)
    specs = [  # (column, score, applied_at)
        ("approved", 90, None),
        ("applied", 80, this_week),
        ("response", 60, now - timedelta(days=10)),
        ("interview", 70, now - timedelta(days=20)),
        ("rejected", 50, now - timedelta(days=25)),
        ("applied", 40, now - timedelta(days=45)),  # outside the 30-day window
        ("offer", 100, now - timedelta(days=60)),  # outside the window
    ]
    for column, score, applied_at in specs:
        card = add(db_session, user, column, score=score)
        if applied_at:
            client.patch(
                f"/tracker/{card['id']}", json={"applied_at": applied_at.isoformat()}
            )
    stats = client.get("/tracker").json()["stats"]
    assert stats["counts"] == {
        "approved": 1, "applied": 2, "response": 1, "interview": 1, "offer": 1, "rejected": 1,
    }  # fmt: skip
    assert stats["applied_this_week"] == (1 if this_week <= now else 0)
    # 30 days: applied/response/interview/rejected were applied; 3 of those 4 responded
    assert stats["response_rate"] == 0.75
    assert stats["avg_match_score"] == pytest.approx(70.0)


def test_stats_with_no_applications(db_session, user):
    add(db_session, user)
    stats = client.get("/tracker").json()["stats"]
    assert stats["response_rate"] is None and stats["applied_this_week"] == 0


def test_stats_use_a_fixed_number_of_aggregate_queries(db_session, user):
    for i in range(12):
        add(db_session, user, "applied", company=str(i))
    seen: list[str] = []

    def spy(conn, cursor, statement, *a):
        seen.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", spy)
    try:
        board = TrackerService(RepositoryManager(db_session)).board(user.id)
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", spy)
    assert len(board.columns["applied"]) == 12
    assert len(seen) == 4  # board rows + stats + average + counts, whatever the size
    assert (
        sum(any(f in s.lower() for f in ("count(", "sum(", "avg(")) for s in seen) == 3
    )


# --- isolation ---------------------------------------------------------------
def test_other_users_cards_are_404_and_invisible(db_session, user):
    card = add(db_session, user)
    other_job = job(db_session, user, company="theirs")
    make_user(db_session, "auth0|B")
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|B"}
    assert (
        client.patch(f"/tracker/{card['id']}", json={"notes": "hi"}).status_code == 404
    )
    assert client.delete(f"/tracker/{card['id']}").status_code == 404
    assert client.post("/tracker", json={"job_id": other_job.id}).status_code == 404
    board = client.get("/tracker").json()
    assert all(v == [] for v in board["columns"].values())
    assert board["stats"]["avg_match_score"] is None
    db_session.expire_all()
    assert db_session.get(TrackerCard, card["id"]).notes is None
