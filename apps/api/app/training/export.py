"""Training dataset export: versioned, consent-gated, PII-scrubbed snapshots.

Sources
- Resumes: only users whose LATEST training-consent row is enabled. Input = the text
  of the uploaded resume file, gold = the user's approved (reviewed) profile that was
  built from that resume.
- JDs: "public + verified" postings from the v1 tables (`jd_extractions` joined to
  `jobs.raw_text`). A JD is verified when ALL hold:
    * the job came from a URL (a public posting, not text a user pasted or a
      screenshot) and finished extraction (status not processing/needs_paste/failed),
    * its raw text is at least MIN_SOURCE_CHARS long,
    * every value of the stored extraction is supported by that raw text (the same
      verbatim check used at extraction time leaves it unchanged).
  SEAM: `catalog_jd_records()` is where Phase 1 `catalog_jobs` plug in later.

Output (storage, never under users/{id}/):
  {prefix}/{version}/train.jsonl and {prefix}/{version}/manifest.json
Records carry no user id, job id or resume id. The manifest has counts, consent
policy versions, the scrub version and a content hash only.

Revoking consent affects FUTURE snapshots only; written snapshots are not rewritten.
"""

import hashlib
import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extractor import MIN_SOURCE_CHARS, docx_text, pdf_text
from app.ai.jd_extractor import verify_verbatim
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.job import JdExtraction, Job
from app.models.profile import APPROVED, Profile
from app.models.resume import Resume
from app.models.user import User
from app.schemas.job import JobDescription
from app.services.training import consented_users
from app.tasks.jobs import TaskContext
from app.training.scrub import SCRUB_VERSION, Scrubber, strip_ids

log = logging.getLogger(__name__)

_UNFINISHED = ("processing", "needs_paste", "failed")


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _record(kind: str, text: str, gold: dict, scrubber: Scrubber) -> dict[str, Any]:
    clean_text = scrubber.text(text)
    clean_gold = scrubber.obj(strip_ids(gold))
    return {
        "kind": kind,
        "record_id": _digest(kind, clean_text)[:32],
        "input_text": clean_text,
        "gold": clean_gold,
    }


# --- resumes ------------------------------------------------------------------
def resume_records(
    ctx: TaskContext, session: Session, consent: dict
) -> Iterator[tuple[dict, str]]:
    """Yield (record, policy_version) for each consenting user's resume."""
    if not consent:
        return
    profiles = session.scalars(
        select(Profile)
        .where(
            Profile.user_id.in_(list(consent)),
            Profile.status == APPROVED,
            Profile.resume_id.is_not(None),
        )
        .order_by(Profile.resume_id, Profile.version.desc())
    )
    seen: set[str] = set()
    for profile in profiles:
        if profile.resume_id in seen:  # latest approved version only
            continue
        seen.add(profile.resume_id)
        resume = session.get(Resume, profile.resume_id)
        if resume is None or resume.user_id != profile.user_id:
            continue
        try:
            data = ctx.storage.read(resume.storage_key)
        except Exception as e:  # noqa: BLE001 - a missing file skips one record
            log.warning("training: resume unreadable error=%s", type(e).__name__)
            continue
        try:
            text = pdf_text(data) if data.startswith(b"%PDF-") else docx_text(data)
        except AppError:
            continue
        if len(text) < MIN_SOURCE_CHARS:
            continue
        user = session.get(User, profile.user_id)
        contact = (profile.data or {}).get("contact") or {}
        scrubber = Scrubber(
            seed=_digest(SCRUB_VERSION, "resume", profile.id),
            names=[contact.get("name") or "", getattr(user, "name", None) or ""],
            emails=[contact.get("email") or "", getattr(user, "email", None) or ""],
            phones=[contact.get("phone") or ""],
            links=contact.get("links") or [],
            locations=[contact.get("location") or ""],
        )
        yield _record("profile", text, profile.data, scrubber), consent[profile.user_id]


# --- JDs ----------------------------------------------------------------------
def is_verified_jd(job: Job, jd: JobDescription) -> bool:
    raw = job.raw_text or ""
    if job.source != "url" or job.status in _UNFINISHED:
        return False
    if len(raw) < MIN_SOURCE_CHARS:
        return False
    return verify_verbatim(jd, raw) == jd


def v1_jd_records(session: Session) -> Iterator[dict]:
    rows = session.execute(
        select(JdExtraction, Job).join(Job, Job.id == JdExtraction.job_id)
    )
    for extraction, job in rows:
        try:
            jd = JobDescription.model_validate(extraction.jd)
        except ValueError:
            continue
        if not is_verified_jd(job, jd):
            continue
        scrubber = Scrubber(seed=_digest(SCRUB_VERSION, "jd", job.id))
        yield _record("jd", job.raw_text or "", jd.model_dump(), scrubber)


def catalog_jd_records(session: Session) -> Iterator[dict]:
    """Seam for Phase 1 `catalog_jobs` (shared, public). Nothing to read yet."""
    return iter(())


# --- snapshot -----------------------------------------------------------------
def next_version(ctx: TaskContext) -> str:
    prefix = settings.training_snapshot_prefix.strip("/")
    taken = [
        int(m.group(1))
        for key in ctx.storage.list_prefix(f"{prefix}/")
        if (m := re.match(rf"{re.escape(prefix)}/v(\d+)/", key))
    ]
    return f"v{max(taken, default=0) + 1:04d}"


def export_training_dataset(ctx: TaskContext, version: str | None = None) -> str:
    """Write a new snapshot and return its version. Never overwrites an old one."""
    prefix = settings.training_snapshot_prefix.strip("/")
    with ctx.session_factory() as session:
        consent = consented_users(session)
        resumes = list(resume_records(ctx, session, consent))
        jds = list(v1_jd_records(session)) + list(catalog_jd_records(session))

    version = version or next_version(ctx)
    if ctx.storage.list_prefix(f"{prefix}/{version}/"):
        raise ValueError(f"snapshot {version} already exists")

    records = [r for r, _ in resumes]
    seen: set[str] = {r["record_id"] for r in records}
    for r in jds:  # identical postings collapse to one record
        if r["record_id"] not in seen:
            seen.add(r["record_id"])
            records.append(r)
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()

    policies: dict[str, int] = {}
    for _, policy in resumes:
        policies[policy] = policies.get(policy, 0) + 1
    manifest = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "scrub_version": SCRUB_VERSION,
        "counts": {
            "profile": sum(r["kind"] == "profile" for r in records),
            "jd": sum(r["kind"] == "jd" for r in records),
            "total": len(records),
        },
        "consent_policy_versions": dict(sorted(policies.items())),
        "train_sha256": hashlib.sha256(body).hexdigest(),
        "verified_jd_rule": "url-sourced, extracted, raw text >= MIN_SOURCE_CHARS, "
        "all values verbatim in source",
    }
    # train.jsonl first: a manifest only exists for a complete snapshot.
    ctx.storage.save(f"{prefix}/{version}/train.jsonl", body)
    ctx.storage.save(
        f"{prefix}/{version}/manifest.json", json.dumps(manifest, indent=2).encode()
    )
    log.info(
        "training snapshot version=%s profiles=%d jds=%d",
        version,
        manifest["counts"]["profile"],
        manifest["counts"]["jd"],
    )
    return version
