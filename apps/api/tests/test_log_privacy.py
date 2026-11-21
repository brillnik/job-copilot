"""Logs may carry ids, statuses, counts and hashes: never resume text, contact
details or CTC. Drive every new flow with recognisable values and grep the output."""

import logging
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import token_claims
from app.main import app
from app.models.run import Draft
from app.tasks import account as acct
from tests.account_helpers import seed
from tests.jobs_helpers import make_ctx
from tests.test_settings import VALID

SECRETS = ["ALPHA", "alpha", "Ada", "Kafka", "@x.co", "31.25", "18.5", "Co ", "posting"]


def test_no_personal_data_in_logs(db_session, tmp_path, caplog):
    client = TestClient(app)
    user, run, waiting = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    app.dependency_overrides[token_claims] = lambda: {
        "sub": "auth0|A",
        "iat": int(time.time()) - 5,
    }
    caplog.set_level(logging.DEBUG, logger="app")
    caplog.clear()

    client.put(
        "/settings", json=VALID | {"current_ctc_lpa": 18.5, "expected_ctc_lpa": 31.25}
    )
    client.get("/runs")
    client.get(f"/runs/{run.id}")
    r2 = client.post(
        f"/runs/{waiting.id}/answer",
        json={
            "answers": [
                {"skill": "Kubernetes", "answer": "yes", "detail": "ran ALPHA clusters"}
            ]
        },
    )
    assert r2.status_code == 202
    client.post("/me/consent", json={"policy_version": "1"})
    client.get("/tracker")
    export_id = client.post("/me/export").json()["export_id"]
    acct.export_user(make_ctx(db_session, tmp_path), user.id, export_id)
    # a refused edit must not echo what was refused
    in_review = db_session.scalar(select(Draft).where(Draft.run_id == run.id))
    assert in_review is not None
    client.post("/auth/logout-all")
    app.dependency_overrides[token_claims] = lambda: {
        "sub": "auth0|A",
        "iat": int(time.time()) + 5,
    }
    client.request("DELETE", "/me", json={"confirm": "DELETE"})
    acct.delete_user(make_ctx(db_session, tmp_path), user.id)

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert len(caplog.records) > 20  # the flows really did log
    leaked = [s for s in SECRETS if s in text]
    assert leaked == [], f"personal data in logs: {leaked}"
    assert str(user.id) in text  # ids are fine
