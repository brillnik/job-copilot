"""Migrations run on a fresh database and on one that already holds data."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

API = Path(__file__).resolve().parents[1]


def alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    done = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=False,
        cwd=API,
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr[-2000:]


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path / 'm.db'}"


def test_fresh_database_matches_the_models(url):
    alembic(url, "upgrade", "head")
    alembic(url, "upgrade", "head")  # re-running is a no-op
    alembic(url, "check")  # no drift between migrations and models


def test_existing_database_keeps_its_data(url):
    alembic(url, "upgrade", "0004")
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(
            sa.text(
                "insert into users(id, auth0_sub, created_at, updated_at) values ('u1','s',current_timestamp,current_timestamp)"
            )
        )
        c.execute(
            sa.text(
                "insert into jobs(id,user_id,source,status,musts,red_flags,created_at,updated_at) values ('j1','u1','text','tailoring','[]','[]',current_timestamp,current_timestamp)"
            )
        )
        c.execute(
            sa.text(
                "insert into agent_runs(id,user_id,job_id,profile_version,status,created_at) values ('r1','u1','j1',1,'awaiting_input',current_timestamp)"
            )
        )
        c.execute(
            sa.text(
                "insert into user_answers(id,user_id,skill,answer,updated_at) values ('a1','u1','go','yes',current_timestamp)"
            )
        )
    alembic(url, "upgrade", "head")
    with engine.connect() as c:
        run = c.execute(
            sa.text("select status, flagged, iteration, event_seq from agent_runs")
        ).one()
        assert tuple(run) == ("waiting_for_user", 0, 0, 0)
        assert c.execute(
            sa.text("select status, preferences_rev from users")
        ).one() == ("active", 0)
        assert c.execute(sa.text("select skill, detail from user_answers")).one() == (
            "go",
            None,
        )
        # the one-active-run-per-job rule follows the renamed status
        with pytest.raises(sa.exc.IntegrityError):
            c.execute(
                sa.text(
                    "insert into agent_runs(id,user_id,job_id,profile_version,status,created_at,updated_at) values ('r2','u1','j1',1,'queued',current_timestamp,current_timestamp)"
                )
            )


def test_downgrade_then_upgrade_round_trips(url):
    alembic(url, "upgrade", "head")
    alembic(url, "downgrade", "0004")
    tables = set(sa.inspect(sa.create_engine(url)).get_table_names())
    assert not tables & {
        "drafts",
        "approvals",
        "tracker_cards",
        "run_events",
        "exports",
    }
    alembic(url, "upgrade", "head")
