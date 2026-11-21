"""Seed one user with a row (and file) in every table the export/delete must cover."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import token_claims
from app.main import app
from app.models.account import ConsentLog, Export
from app.models.email import EmailEvent, GmailConnection
from app.models.job import Event, ImageUpload, UserAnswer
from app.models.resume import Resume
from app.models.run import Approval
from app.models.screening import ScreeningAnswer
from app.models.training import TrainingConsentLog
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from tests.jobs_helpers import approve_profile, make_job, make_user
from tests.runs_helpers import run_ready


def seed(db, tmp_path, sub: str, marker: str):
    """Everything a busy user has. `marker` appears in their data so leaks are greppable."""
    client = TestClient(app)
    user = make_user(db, sub)
    user.preferences = {"target_roles": [marker]}
    user.name = f"name-{marker}"
    profile = ProfileData(
        contact=Contact(name=f"Ada {marker}", location="Bengaluru"),
        skills=["Python"],
        experience=[
            Experience(
                id="e1",
                company="Acme",
                bullets=[Bullet(id="b1", text=f"Built Kafka pipelines {marker}")],
            )
        ],
    )
    approve_profile(db, user, profile)
    job = make_job(
        db, user, JobDescription(company=f"Co {marker}"),
        company=f"Co {marker}", title="Engineer", score=70, raw_text=f"posting {marker} " * 30,
    )  # fmt: skip
    run = run_ready(db, tmp_path, user, job=job)
    waiting = run_ready(db, tmp_path, user, status="waiting_for_user")
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}
    assert (
        client.post(f"/runs/{run.id}/approve").status_code == 200
    )  # approval, pdf, card
    db.add(UserAnswer(user_id=user.id, skill=f"skill-{marker}", answer="yes"))
    db.add(
        ScreeningAnswer(
            user_id=user.id,
            question=f"q-{marker}",
            normalised_question=f"q-{marker}",
            answer=f"a-{marker}",
            field_type="open",
            embedding=[],
            source="user",
        )
    )
    from app.models.application import Application, ApplyQuota, SiteState

    db.add_all(
        [
            Application(
                user_id=user.id, job_id=job.id, run_id=run.id, channel="playwright",
                ats="greenhouse", site="greenhouse", status="skipped",
                skip_reason="captcha", apply_url=f"https://example.com/{marker}",
            ),
            ApplyQuota(user_id=user.id, day="2026-11-19", site="*", used=1),
            SiteState(user_id=user.id, site="greenhouse", consecutive_blocks=1),
        ]
    )  # fmt: skip
    db.add(ConsentLog(user_id=user.id, policy_version="1"))
    db.add(TrainingConsentLog(user_id=user.id, enabled=True, policy_version="1"))
    resume = Resume(
        user_id=user.id, filename=f"cv-{marker}.pdf", size=9,
        storage_key=f"{user.id.hex}/resume-{marker}.pdf",
    )  # fmt: skip
    image = ImageUpload(
        user_id=user.id, storage_key=f"{user.id.hex}/images/shot-{marker}.png",
        media_type="image/png", size=9,
    )  # fmt: skip
    db.add_all([resume, image])
    db.add(
        GmailConnection(
            user_id=user.id, token_ciphertext=f"cipher-{marker}", email_hash=marker
        )
    )
    db.add(
        EmailEvent(
            user_id=user.id, gmail_message_id=f"m-{marker}", job_id=job.id,
            classification="interview", confidence=0.9,
            received_at=datetime.now(UTC),
        )
    )  # fmt: skip
    # Discovery (v2 phase 1): a recommendation, a paired device and a pairing code.
    from app.models.discovery import (
        ExtensionPairingCode,
        ExtensionToken,
        Recommendation,
    )
    from tests.discovery_helpers import make_catalog

    cat = make_catalog(db, title=f"Role {marker}", external_id=f"x-{marker}")
    db.add_all(
        [
            Recommendation(
                user_id=user.id,
                catalog_job_id=cat.id,
                score=60,
                digest_date="2026-11-19",
            ),
            ExtensionToken(user_id=user.id, token_hash=f"th-{marker}", device_name="d"),
            ExtensionPairingCode(
                user_id=user.id,
                code_hash=f"ch-{marker}",
                expires_at=datetime.now(UTC),
            ),
        ]
    )
    db.commit()
    for key, data in (
        (resume.storage_key, b"%PDF-resume"),
        (image.storage_key, b"png-bytes"),
    ):
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return user, run, waiting


def data_rows(db, user) -> dict[str, int]:
    """Row counts for every table that has user_id, for this user."""
    from app.db.base import Base

    out = {}
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.c and table.name != "users":
            n = db.execute(
                select(__import__("sqlalchemy").func.count())
                .select_from(table)
                .where(table.c.user_id == user.id)
            ).scalar()
            out[table.name] = n
    return out


__all__ = ["Approval", "Event", "Export", "data_rows", "seed"]
