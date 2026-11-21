import json

import pytest

from app.core.config import settings
from app.models.job import Job
from app.models.profile import Profile
from app.models.resume import Resume
from app.models.training import TrainingConsentLog
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from app.services.training import consented_users
from app.tasks.runtime import registry
from app.training.export import export_training_dataset, next_version
from tests.jobs_helpers import approve_profile, make_ctx, make_job, make_user
from tests.test_qwen import docx_bytes

PAD = "Skills: Kafka, Python\n" * 20


def seed_resume(db, ctx, sub, name, email, phone):
    user = make_user(db, sub)
    text = f"{name}\n{email} | {phone}\nSenior Engineer at Acme\n- Built Kafka pipelines\n{PAD}"
    data = ProfileData(
        contact=Contact(name=name, email=email, phone=phone, location="Bengaluru"),
        skills=["Kafka"],
        experience=[
            Experience(company="Acme", bullets=[Bullet(text="Built Kafka pipelines")])
        ],
    )
    profile = approve_profile(db, user, data)
    key = f"users/{user.id.hex}/resume.docx"
    ctx.storage.save(key, docx_bytes(text))
    resume = Resume(user_id=user.id, filename="r.docx", size=9, storage_key=key)
    db.add(resume)
    db.commit()
    row = db.get(Profile, profile.id)
    row.resume_id = resume.id
    db.commit()
    return user


def consent(db, user, enabled, version="v1"):
    db.add(TrainingConsentLog(user_id=user.id, enabled=enabled, policy_version=version))
    db.commit()


def read(ctx, version):
    base = f"{settings.training_snapshot_prefix}/{version}"
    manifest = json.loads(ctx.storage.read(f"{base}/manifest.json"))
    lines = ctx.storage.read(f"{base}/train.jsonl").decode().splitlines()
    return manifest, [json.loads(line) for line in lines]


@pytest.fixture
def world(db_session, tmp_path):
    ctx = make_ctx(db_session, tmp_path)
    a = seed_resume(
        db_session, ctx, "auth0|A", "Priya Raman", "priya@gmail.com", "+91 98765 43210"
    )
    b = seed_resume(
        db_session, ctx, "auth0|B", "Rohan Mehta", "rohan@yahoo.com", "+91 91234 56789"
    )
    c = seed_resume(
        db_session, ctx, "auth0|C", "Sunil Verma", "sunil@proton.me", "+91 90000 11111"
    )
    return ctx, a, b, c


def test_only_consented_users_are_exported(db_session, world):
    ctx, a, _b, c = world
    consent(db_session, a, True)
    consent(db_session, c, False)  # opted in never; b has no row at all
    version = export_training_dataset(ctx)
    manifest, records = read(ctx, version)
    assert manifest["counts"]["profile"] == 1 and len(records) == 1
    raw = ctx.storage.read(f"snapshots/{version}/train.jsonl").decode()
    assert "Priya" not in raw and "Rohan" not in raw and "Sunil" not in raw
    assert records[0]["kind"] == "profile"
    assert "Kafka pipelines" in records[0]["input_text"]
    assert records[0]["gold"]["skills"] == ["Kafka"]


def test_revoked_user_is_excluded_from_future_snapshots_only(db_session, world):
    ctx, a, b, _ = world
    consent(db_session, a, True)
    consent(db_session, b, True)
    v1 = export_training_dataset(ctx)
    consent(db_session, a, False)  # revoke
    v2 = export_training_dataset(ctx)
    assert read(ctx, v1)[0]["counts"]["profile"] == 2
    assert read(ctx, v2)[0]["counts"]["profile"] == 1
    assert consented_users(db_session).keys() == {b.id}
    # re-consent brings the user back
    consent(db_session, a, True, "v2")
    assert read(ctx, export_training_dataset(ctx))[0]["consent_policy_versions"] == {
        "v1": 1,
        "v2": 1,
    }


def test_pii_scrubbed_from_every_output_byte(db_session, world):
    ctx, a, b, c = world
    for u in (a, b, c):
        consent(db_session, u, True)
    version = export_training_dataset(ctx)
    raw = b"".join(
        ctx.storage.read(k) for k in ctx.storage.list_prefix(f"snapshots/{version}/")
    ).decode()
    for leak in (
        "Priya", "Raman", "Rohan", "Mehta", "Sunil", "Verma", "gmail", "yahoo", "proton",
        "98765", "91234", "90000", "Bengaluru", "auth0|", str(a.id), a.id.hex, b.id.hex,
    ):  # fmt: skip
        assert leak not in raw, leak
    _, records = read(ctx, version)
    for r in records:
        c = r["gold"]["contact"]
        assert c["email"] in r["input_text"] and c["name"] in r["input_text"]
        assert c["phone"] in r["input_text"]
    assert "id" not in records[0]["gold"]["experience"][0]


def test_snapshots_are_versioned_and_outside_user_prefix(db_session, world):
    ctx, a, *_ = world
    consent(db_session, a, True)
    v1, v2 = export_training_dataset(ctx), export_training_dataset(ctx)
    assert (v1, v2) == ("v0001", "v0002") and next_version(ctx) == "v0003"
    keys = ctx.storage.list_prefix("snapshots/")
    assert sorted(keys) == [
        f"snapshots/{v}/{f}" for v in (v1, v2) for f in ("manifest.json", "train.jsonl")
    ]
    assert not any(k.startswith("users/") for k in keys)
    m1, _ = read(ctx, v1)
    assert m1["scrub_version"] and len(m1["train_sha256"]) == 64
    # manifest: counts, hashes, policy versions only
    text = json.dumps(m1)
    assert str(a.id) not in text and a.id.hex not in text and "auth0" not in text
    with pytest.raises(ValueError):
        export_training_dataset(ctx, version=v1)  # never overwrite


def test_task_is_registered():
    assert "export_training_dataset" in registry()


# --- JDs ---------------------------------------------------------------------------
POSTING = (
    "Backend Engineer at Acme in Bengaluru. Email jobs@acme.io or call +91 98765 00000. "
    "Must know Kafka. " + "We build things. " * 30
)


def jd_job(db, user, **kw):
    jd = JobDescription(title="Backend Engineer", company="Acme", must_have=["Kafka"])
    return make_job(db, user, jd, source="url", raw_text=POSTING, **kw)


def test_only_verified_public_jds_are_exported(db_session, tmp_path):
    ctx = make_ctx(db_session, tmp_path)
    u = make_user(db_session, "auth0|A")  # not consented: JDs are public anyway
    good = jd_job(db_session, u)
    make_job(  # pasted text, not a public posting
        db_session,
        u,
        JobDescription(title="Backend Engineer"),
        source="text",
        raw_text=POSTING,
    )
    make_job(  # value not in source: unverified
        db_session, u, JobDescription(title="Astronaut"), source="url", raw_text=POSTING
    )
    make_job(
        db_session,
        u,
        JobDescription(title="Backend Engineer"),
        source="url",
        raw_text="short",
    )
    make_job(
        db_session,
        u,
        JobDescription(title="Backend Engineer"),
        source="url",
        raw_text=POSTING,
        status="needs_paste",
    )
    assert good
    version = export_training_dataset(ctx)
    manifest, records = read(ctx, version)
    assert manifest["counts"] == {"profile": 0, "jd": 1, "total": 1}
    r = records[0]
    assert r["kind"] == "jd" and r["gold"]["title"] == "Backend Engineer"
    raw = ctx.storage.read(f"snapshots/{version}/train.jsonl").decode()
    assert "jobs@acme.io" not in raw and "98765" not in raw and str(u.id) not in raw
    assert db_session.query(Job).count() == 5
