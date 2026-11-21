"""Account tasks: data export and account deletion.

Logs carry ids and counts only: never names, emails, resume text or file names.
"""

import io
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from app.core.clock import as_utc
from app.core.privacy import hash_sub, hash_user_id
from app.models.account import ConsentLog, DeletionAudit, Export
from app.models.application import Application, ApplyQuota, SiteState
from app.models.discovery import ExtensionPairingCode, ExtensionToken, Recommendation
from app.models.email import EmailEvent, GmailConnection
from app.models.job import (
    AgentRun,
    Event,
    ImageUpload,
    JdExtraction,
    Job,
    RunQuota,
    UserAnswer,
)
from app.models.profile import Profile, ProfileBullet
from app.models.resume import Resume
from app.models.run import Approval, Draft, RunEvent
from app.models.screening import ScreeningAnswer
from app.models.tracker import TrackerCard
from app.models.training import TrainingConsentLog
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.services import crypto
from app.services.account import export_expiry
from app.tasks.jobs import TaskContext

log = logging.getLogger(__name__)

# Child tables first, so foreign keys hold on Postgres. Every table carrying user_id
# must be listed (a test enforces it); the user row itself goes last.
PURGE_ORDER = (
    Application,
    ApplyQuota,
    SiteState,
    Recommendation,
    ExtensionToken,
    ExtensionPairingCode,
    EmailEvent,
    GmailConnection,
    RunEvent,
    Draft,
    Approval,
    AgentRun,
    TrackerCard,
    JdExtraction,
    Job,
    ImageUpload,
    ProfileBullet,  # the embedding vectors live in these rows
    Profile,
    Resume,
    Event,
    UserAnswer,
    ScreeningAnswer,
    RunQuota,
    ConsentLog,
    TrainingConsentLog,
    Export,
)


def export_key(user_id: uuid.UUID, export_id: str) -> str:
    return f"users/{user_id.hex}/exports/{export_id}.zip.enc"


def _row(obj: Any, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        a.key: getattr(obj, a.key)
        for a in inspect(obj).mapper.column_attrs
        if a.key not in skip
    }


def _json(data: Any) -> bytes:
    return json.dumps(data, default=str, indent=2).encode()


# --- export -----------------------------------------------------------------
def build_export(ctx: TaskContext, repos: RepositoryManager, user: User) -> bytes:
    """A zip of everything we hold for this user. Every query is scoped by user_id."""
    s, uid = repos.session, user.id

    def rows(model, order=None):
        stmt = select(model).where(model.user_id == uid)
        return list(s.scalars(stmt.order_by(order) if order is not None else stmt))

    buf = io.BytesIO()
    missing: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:

        def add_file(arcname: str, key: str | None) -> None:
            if not key:
                return
            try:
                z.writestr(arcname, ctx.storage.read(key))
            except Exception:  # noqa: BLE001 - one missing file must not sink the export
                missing.append(arcname)

        # Profile versions; the embedding vectors are derived data and left out.
        z.writestr(
            "profiles.json", _json([_row(p) for p in rows(Profile, Profile.created_at)])
        )
        z.writestr(
            "jobs.json",
            _json([_row(j) for j in rows(Job)]),
        )
        z.writestr("jd_extractions.json", _json([_row(x) for x in rows(JdExtraction)]))
        drafts = rows(Draft, Draft.created_at)
        approvals = rows(Approval, Approval.created_at)
        z.writestr(
            "runs.json", _json([_row(r) for r in rows(AgentRun, AgentRun.created_at)])
        )
        z.writestr(
            "run_events.json", _json([_row(e) for e in rows(RunEvent, RunEvent.id)])
        )
        z.writestr("drafts.json", _json([_row(d) for d in drafts]))
        z.writestr("approvals.json", _json([_row(a) for a in approvals]))
        z.writestr("tracker.json", _json([_row(c) for c in rows(TrackerCard)]))
        # No subjects, senders or bodies are ever stored, so this is all of it.
        z.writestr("email_events.json", _json([_row(e) for e in rows(EmailEvent)]))
        z.writestr("answers.json", _json([_row(a) for a in rows(UserAnswer)]))
        z.writestr(
            "recommendations.json", _json([_row(r) for r in rows(Recommendation)])
        )
        applications = rows(Application)
        z.writestr("applications.json", _json([_row(a) for a in applications]))
        z.writestr(  # device tokens without their hashes
            "extension_devices.json",
            _json([_row(t, ("token_hash",)) for t in rows(ExtensionToken)]),
        )
        z.writestr(
            "consent.json",
            _json([_row(c) for c in rows(ConsentLog, ConsentLog.created_at)]),
        )
        z.writestr(
            "training_consent.json",
            _json([_row(c) for c in rows(TrainingConsentLog, TrainingConsentLog.id)]),
        )
        z.writestr(
            "settings.json",
            _json(
                {
                    "preferences": user.preferences,
                    "preferences_rev": user.preferences_rev,
                    "autopilot": user.autopilot,
                }
            ),
        )
        for r in rows(Resume):
            add_file(f"files/resumes/{r.id}-{r.filename}", r.storage_key)
        for i in rows(ImageUpload):
            add_file(
                f"files/uploads/{i.id}-{i.storage_key.rsplit('/', 1)[-1]}",
                i.storage_key,
            )
        for d in drafts:
            add_file(f"files/drafts/{d.run_id}-{d.iteration}.pdf", d.pdf_key)
        for a in approvals:
            add_file(f"files/approved/{a.file_name or a.run_id + '.pdf'}", a.pdf_key)
        for ap in applications:
            for n, k in enumerate(ap.screenshot_keys or []):
                add_file(f"files/applications/{ap.id}-{n}.png", k)
        if missing:
            z.writestr("missing_files.json", _json(missing))
    return buf.getvalue()


def export_user(ctx: TaskContext, user_id: uuid.UUID | str, export_id: str) -> None:
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        export = repos.accounts.get_export(user_id, export_id)
        user = repos.users.get(user_id)
        if export is None or user is None or export.status not in ("queued", "running"):
            log.info("export_user skipped export=%s", export_id)
            return
        export.status = "running"
        session.commit()
        try:
            data = crypto.encrypt(build_export(ctx, repos, user))
            key = export_key(user_id, export.id)
            ctx.storage.save(key, data)
        except Exception as e:  # noqa: BLE001 - a task must never die silently
            session.rollback()
            export.status = "failed"
            session.commit()
            log.error(
                "export_user failed export=%s error=%s", export_id, type(e).__name__
            )
            return
        now = datetime.now(UTC)
        export.status, export.storage_key = "ready", key
        export.ready_at, export.expires_at = now, export_expiry(now)
        repos.jobs.stage_event(user_id, "export_ready", {"export_id": export.id})
        session.commit()
        if ctx.mailer is not None:
            ctx.mailer.send(str(user_id), "export_ready", export_id=export.id)
        log.info("export_user ready export=%s bytes=%d", export.id, len(data))


def expire_exports(ctx: TaskContext) -> int:
    """Delete archives past their 7 days. Run daily (scheduler is a TODO)."""
    count = 0
    with ctx.session_factory() as session:
        now = datetime.now(UTC)
        for export in session.scalars(select(Export).where(Export.status == "ready")):
            if export.expires_at is None or as_utc(export.expires_at) > now:
                continue
            if export.storage_key:
                ctx.storage.delete(export.storage_key)
            export.status, export.storage_key = "expired", None
            count += 1
        session.commit()
    log.info("expire_exports expired=%d", count)
    return count


# --- delete -----------------------------------------------------------------
def purge_data(session: Session, user_id: uuid.UUID) -> None:
    """Hard-delete every row of this user, one committed step per table."""
    for model in PURGE_ORDER:
        session.execute(delete(model).where(model.user_id == user_id))
        session.commit()


def delete_user(ctx: TaskContext, user_id: uuid.UUID | str) -> None:
    """Erase an account. Safe to re-run after a crash at any point.

    Files go first, then rows table by table, then the user row together with the
    audit record. The user row is what marks the job unfinished, so a crash anywhere
    before the last commit just means the next run (resume_deletions) starts over.
    """
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        user = session.get(User, user_id)
        if user is not None and user.status != "deleting":
            log.warning(
                "delete_user refused: account is not marked deleting user=%s", user_id
            )
            return
        hexid = user_id.hex
        # `users/{id}/` is the current layout; `{id}/` is where early uploads went.
        files = ctx.storage.delete_prefix(f"users/{hexid}/")
        files += ctx.storage.delete_prefix(f"{hexid}/")
        purge_data(session, user_id)
        if user is not None:
            audited = session.scalar(
                select(DeletionAudit.id).where(
                    DeletionAudit.user_id_hash == hash_user_id(user_id)
                )
            )
            if audited is None:
                session.add(
                    DeletionAudit(
                        user_id_hash=hash_user_id(user_id),
                        sub_hash=hash_sub(user.auth0_sub),
                    )
                )
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
        # A task that was mid-flight when deletion began may have written after the
        # first pass; sweep once more.
        purge_data(session, user_id)
        log.info("delete_user done user=%s files=%d", user_id, files)


def resume_deletions(ctx: TaskContext) -> int:
    """Finish any deletion that did not complete. Schedule at least hourly (TODO)."""
    with ctx.session_factory() as session:
        ids = list(session.scalars(select(User.id).where(User.status == "deleting")))
    for uid in ids:
        delete_user(ctx, uid)
    return len(ids)
