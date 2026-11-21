"""Run review: list/detail, answers, edits, approve/reject/regenerate/cancel, PDF links.

Logs carry ids, statuses and counts only: never resume text, contact details or CTC.
"""

import logging
import uuid

from sqlalchemy.exc import IntegrityError

from app.agent.diff import word_diff
from app.agent.fact_check import (
    Facts,
    build_facts,
    check_bullet,
    check_prose,
    check_skills,
    fact_check,
)
from app.agent.pdf import slug
from app.core import signing
from app.core.config import settings
from app.core.exceptions import AppError, Conflict, NotFound
from app.models.job import AgentRun
from app.models.run import Approval, Draft
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription, TailorIn
from app.schemas.profile import ProfileData
from app.schemas.run import (
    ApproveOut,
    BulletReview,
    Coverage,
    DraftEdit,
    DraftEditOut,
    IterationOut,
    Pages,
    PendingQuestion,
    RegenerateIn,
    RejectIn,
    RunDetail,
    RunList,
    RunRef,
    RunSummary,
    TailoredBullet,
    TailoredResume,
    Violation,
)
from app.services import paging
from app.services.job import Invalid, JobService
from app.services.profile import ProfileService
from app.services.run_state import IllegalTransition, transition
from app.services.tracker import TrackerService
from app.storage.base import Storage
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _coverage_text(cov: dict | None) -> str | None:
    if not cov:
        return None
    total = len(cov.get("covered", [])) + len(cov.get("missing", []))
    return f"{len(cov.get('covered', []))}/{total}" if total else None


class RunService:
    def __init__(
        self,
        repos: RepositoryManager,
        queue: TaskQueue,
        storage: Storage,
        jobs: JobService,
        profiles: ProfileService,
    ) -> None:
        self.repos = repos
        self.queue = queue
        self.storage = storage
        self.jobs = jobs
        self.profiles = profiles
        self.tracker = TrackerService(repos)
        self._profile_cache: dict[tuple[uuid.UUID, int], ProfileData] = {}

    def _own(self, user_id: uuid.UUID, run_id: str) -> AgentRun:
        run = self.repos.runs.get_for_user(user_id, run_id)
        if run is None:
            # Also what a request for someone else's run looks like.
            log.info("run not found user=%s run=%s", user_id, run_id)
            raise NotFound("Run not found")
        return run

    def _profile_data(self, run: AgentRun) -> ProfileData:
        """The run's pinned profile version; cached so listing many runs reads each once."""
        key = (run.user_id, run.profile_version)
        if key not in self._profile_cache:
            profile = self.repos.profiles.get_version(*key)
            self._profile_cache[key] = (
                ProfileData.model_validate(profile.data) if profile else ProfileData()
            )
        return self._profile_cache[key]

    # --- read ----------------------------------------------------------------
    def list_runs(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        job_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> RunList:
        offset = paging.decode(cursor)
        rows = self.repos.runs.list_for_user(
            user_id, status=status, job_id=job_id, offset=offset, limit=limit + 1
        )
        page = rows[:limit]
        jobs = self.repos.runs.jobs_for(user_id, [r.job_id for r in page])
        drafts = self.repos.runs.latest_drafts(user_id, [r.id for r in page])
        items = []
        for r in page:
            job, d = jobs.get(r.job_id), drafts.get(r.id)
            items.append(
                RunSummary(
                    id=r.id,
                    job_id=r.job_id,
                    company=job.company if job else None,
                    title=job.title if job else None,
                    status=r.status,
                    flagged=r.flagged,
                    score=job.score if job else None,
                    coverage=_coverage_text(d.coverage) if d else None,
                    pages=(d.pages or {}).get("count") if d else None,
                    created_at=r.created_at,
                    top_changes=self._top_changes(user_id, r, d),
                )
            )
        log.debug("run list user=%s status=%s -> %d", user_id, status, len(page))
        return RunList(
            items=items,
            next_cursor=paging.encode(offset + limit) if len(rows) > limit else None,
        )

    def _top_changes(
        self, user_id: uuid.UUID, run: AgentRun, draft: Draft | None
    ) -> list[str]:
        if draft is None:
            return []
        sources = self._source_texts(run)
        out = []
        for b in draft.tailored.get("bullets", []):
            if b.get("reverted") or b["text"] == sources.get(b["source_id"]):
                continue
            out.append("Reworded: " + _truncate(b["text"], 60))
            if len(out) == 3:
                break
        return out

    def _source_texts(self, run: AgentRun) -> dict[str, str]:
        data = self._profile_data(run)
        texts = {b.id: b.text for e in data.experience for b in e.bullets}
        return texts | {b.id: b.text for p in data.projects for b in p.bullets}

    def detail(self, user_id: uuid.UUID, run_id: str) -> RunDetail:
        return self._detail(self._own(user_id, run_id))

    def _detail(self, run: AgentRun) -> RunDetail:
        user_id = run.user_id
        job = self.repos.jobs.get_for_user(user_id, run.job_id)
        draft = self.repos.runs.latest_draft(user_id, run.id)
        history = self.repos.runs.drafts(user_id, run.id)
        sources = self._source_texts(run)
        tailored = TailoredResume.model_validate(draft.tailored) if draft else None
        bullets = [
            BulletReview(
                source_id=b.source_id,
                source_text=sources.get(b.source_id),
                tailored_text=b.text,
                diff=word_diff(sources.get(b.source_id) or "", b.text),
                reverted=b.reverted,
                revert_reason=b.revert_reason,
            )
            for b in (tailored.bullets if tailored else [])
        ]
        return RunDetail(
            id=run.id,
            job_id=run.job_id,
            company=job.company if job else None,
            title=job.title if job else None,
            status=run.status,
            status_reason=run.status_reason,
            flagged=run.flagged,
            current_step=run.current_step,
            iteration=run.iteration,
            profile_version=run.profile_version,
            max_pages=run.max_pages,
            pending_questions=[
                PendingQuestion(**q) for q in run.pending_questions or []
            ],
            created_at=run.created_at,
            updated_at=run.updated_at,
            draft_rev=draft.rev if draft else None,
            edited=bool(draft and draft.edited),
            summary=tailored.summary if tailored else None,
            skills_order=tailored.skills_order if tailored else [],
            cover_note=tailored.cover_note if tailored else None,
            bullets=bullets,
            violations=[Violation(**v) for v in (draft.violations if draft else [])],
            coverage=Coverage(**draft.coverage) if draft and draft.coverage else None,
            pages=Pages(**draft.pages) if draft and draft.pages else None,
            iterations=[
                IterationOut(iteration=d.iteration, outcome=d.outcome) for d in history
            ],
            has_pdf=bool(draft and draft.pdf_key),
        )

    # --- answer --------------------------------------------------------------
    def answer(self, user_id: uuid.UUID, run_id: str, body) -> RunRef:
        run = self._own(user_id, run_id)
        if run.status != "waiting_for_user":
            raise IllegalTransition(
                "This run is not waiting for answers",
                details={"from": run.status, "to": "queued"},
            )
        asked = {q["skill"].strip().lower() for q in run.pending_questions or []}
        unknown = sorted(
            {a.skill for a in body.answers if a.skill.strip().lower() not in asked}
        )
        if unknown:
            raise Invalid(
                "Answers for skills the run did not ask about",
                details={"skills": unknown},
            )
        for a in body.answers:
            self.repos.runs.stage_upsert_answer(
                user_id, a.skill, a.answer, a.detail if a.answer == "yes" else None
            )
        run.pending_questions = []
        transition(self.repos, run, "queued", reason="answered")  # one commit for all
        self.queue.enqueue("tailor", user_id=str(user_id), run_id=run.id, resume=True)
        for a in body.answers:
            if a.answer == "yes" and a.detail:
                # The fact joins the profile draft through the profile service, so it
                # takes effect on resumes only once the user approves that draft.
                try:
                    self.profiles.add_confirmed_skill(user_id, a.skill.strip())
                except Exception as e:  # noqa: BLE001 - the run is already resumed
                    log.error(
                        "answer: profile draft update failed error=%s", type(e).__name__
                    )
        log.info(
            "run answered user=%s run=%s answers=%d", user_id, run.id, len(body.answers)
        )
        return RunRef(run_id=run.id, status=run.status)

    # --- edit draft ----------------------------------------------------------
    def _facts(self, run: AgentRun) -> Facts:
        ext = self.repos.jobs.extraction_for(run.user_id, run.job_id)
        jd = JobDescription.model_validate(ext.jd) if ext else JobDescription()
        return build_facts(
            self._profile_data(run),
            self.repos.runs.answers_full(run.user_id),
            extra_terms=[*jd.must_have, *jd.nice_to_have, *jd.keywords],
            synonyms=settings.skill_synonyms,
        )

    def edit_draft(
        self,
        user_id: uuid.UUID,
        run_id: str,
        body: DraftEdit,
        if_match: int | None,
    ) -> DraftEditOut:
        run = self._own(user_id, run_id)
        if run.status != "in_review":
            raise IllegalTransition(
                "Only a run in review can be edited",
                details={"from": run.status, "to": "in_review"},
            )
        draft = self.repos.runs.latest_draft(user_id, run_id)
        if draft is None:
            raise Conflict("The run has no draft yet", code="no_draft")
        facts = self._facts(run)
        tailored = TailoredResume.model_validate(draft.tailored)
        fields = body.model_fields_set
        applied: list[str] = []
        blocked: list[Violation] = []

        def refuse(found: list[Violation]) -> None:
            blocked.extend(v.model_copy(update={"blocked": True}) for v in found)

        for name in ("summary", "cover_note"):
            if name in fields:
                text = getattr(body, name)
                found = check_prose(facts, name, text)
                if found:
                    refuse(found)
                else:
                    setattr(tailored, name, text)
                    applied.append(name)
        if "skills_order" in fields:
            found = check_skills(facts, body.skills_order or [])
            if found:
                refuse(found)
            else:
                tailored.skills_order = body.skills_order or []
                applied.append("skills_order")
        by_id = {b.source_id: b for b in tailored.bullets}
        for edit in body.bullets or []:
            target = by_id.get(edit.source_id)
            if target is None:
                refuse(
                    [
                        Violation(
                            code="unknown_source",
                            field="bullet",
                            source_id=edit.source_id,
                            message="This bullet is not in the draft",
                        )
                    ]
                )
                continue
            found = check_bullet(
                facts, TailoredBullet(source_id=edit.source_id, text=edit.text)
            )
            if found:
                refuse(found)
            else:
                target.text, target.reverted, target.revert_reason = (
                    edit.text,
                    False,
                    None,
                )
                applied.append(f"bullet:{edit.source_id}")

        if applied:
            expected = draft.rev if if_match is None else if_match
            if not self.repos.runs.cas_draft_rev(user_id, draft, expected):
                self.repos.session.rollback()
                self.repos.session.refresh(draft)
                log.info("draft stale write user=%s run=%s", user_id, run_id)
                raise Conflict(
                    "The draft changed since you loaded it",
                    code="stale_write",
                    details={"rev": draft.rev},
                )
            old_pdf = draft.pdf_key
            draft.tailored = tailored.model_dump()
            draft.violations = [v.model_dump() for v in fact_check(facts, tailored)]
            draft.edited, draft.pdf_key = True, None  # the old PDF no longer matches
            self.repos.runs.stage_event(
                run, "draft_edited", {"iteration": draft.iteration, "fields": applied}
            )
            self.repos.session.commit()
            if old_pdf:
                self.storage.delete(old_pdf)
            self.queue.enqueue(
                "render_pdf",
                user_id=str(user_id),
                run_id=run.id,
                iteration=draft.iteration,
            )
        elif if_match is not None and if_match != draft.rev:
            raise Conflict(
                "The draft changed since you loaded it",
                code="stale_write",
                details={"rev": draft.rev},
            )
        log.info(
            "draft edited user=%s run=%s applied=%d blocked=%d",
            user_id,
            run.id,
            len(applied),
            len(blocked),
        )
        remaining = [Violation(**v) for v in draft.violations]
        return DraftEditOut(
            run=self._detail(run), applied=applied, violations=[*blocked, *remaining]
        )

    # --- approve / reject ----------------------------------------------------
    def _file_name(self, user_id: uuid.UUID, run: AgentRun, company: str | None) -> str:
        name = self._profile_data(run).contact.name
        if not name:
            user = self.repos.users.get(user_id)
            name = user.name if user else None
        parts = [p for p in slug(name, keep_case=True, default="").split("-") if p]
        person = (
            f"{parts[0]}-{parts[-1]}"
            if len(parts) > 1
            else (parts[0] if parts else "resume")
        )
        return f"{person}_{slug(company)}.pdf"

    def approve(self, user_id: uuid.UUID, run_id: str) -> ApproveOut:
        run = self._own(user_id, run_id)
        existing = self.repos.runs.approval_for(user_id, run_id)
        if existing is not None:
            if existing.decision == "approved":
                return ApproveOut(
                    approval_id=existing.id, file_name=existing.file_name or ""
                )
            raise IllegalTransition(
                "This run was rejected", details={"from": run.status, "to": "approved"}
            )
        if run.status != "in_review":
            raise IllegalTransition(
                f"A run that is {run.status} cannot be approved",
                details={"from": run.status, "to": "approved"},
            )
        draft = self.repos.runs.latest_draft(user_id, run_id)
        if draft is None:
            raise Conflict("The run has no draft yet", code="no_draft")
        if not draft.pdf_key:
            raise Conflict("The PDF is still being prepared", code="pdf_not_ready")
        job = self.repos.jobs.get_for_user(user_id, run.job_id)
        file_name = self._file_name(user_id, run, job.company if job else None)
        key = f"users/{user_id.hex}/resumes/{run.id}.pdf"
        jd_vec, jd_model = self._jd_embedding(user_id, run.job_id)
        self.storage.save(key, self.storage.read(draft.pdf_key))
        try:
            approval = self.repos.runs.stage_approval(
                Approval(
                    user_id=user_id,
                    run_id=run.id,
                    job_id=run.job_id,
                    decision="approved",
                    reasons=[],
                    edits_applied=draft.edited,
                    final=draft.tailored,
                    pdf_key=key,
                    file_name=file_name,
                    jd_embedding=jd_vec,
                    jd_embedding_model=jd_model,
                )
            )
            transition(self.repos, run, "approved", commit=False)
            self.tracker.upsert_for_approval(user_id, run.job_id)
            self.repos.session.flush()
            self.repos.jobs.stage_event(
                user_id,
                "run_approved",
                {"run_id": run.id, "job_id": run.job_id, "approval_id": approval.id},
            )
            self.repos.runs.stage_event(run, "approved", {"approval_id": approval.id})
            self.repos.session.commit()
        except (IntegrityError, IllegalTransition):
            # A concurrent approve won: report its result.
            self.repos.session.rollback()
            won = self.repos.runs.approval_for(user_id, run_id)
            if won is not None and won.decision == "approved":
                return ApproveOut(approval_id=won.id, file_name=won.file_name or "")
            self._drop_copy(user_id, run_id, key)
            raise
        except Exception:
            self.repos.session.rollback()
            self._drop_copy(user_id, run_id, key)
            raise
        log.info(
            "run approved user=%s run=%s approval=%s", user_id, run.id, approval.id
        )
        return ApproveOut(approval_id=approval.id, file_name=file_name)

    def _jd_embedding(self, user_id: uuid.UUID, job_id: str):
        """(vector, model) of the job's title + must-haves; (None, None) if unavailable."""
        try:
            from app.agent.examples import embed_jd

            ext = self.repos.jobs.extraction_for(user_id, job_id)
            embedder = getattr(self.profiles, "embedder", None)
            if ext is None or embedder is None:
                return None, None
            vec = embed_jd(embedder, JobDescription.model_validate(ext.jd))
            return (vec, embedder.name) if vec else (None, None)
        except Exception as e:  # noqa: BLE001 - examples are optional; never block approve
            log.warning(
                "jd embedding skipped run=%s error=%s", job_id, type(e).__name__
            )
            return None, None

    def _drop_copy(self, user_id: uuid.UUID, run_id: str, key: str) -> None:
        if self.repos.runs.approval_for(user_id, run_id) is None:
            self.storage.delete(key)

    def reject(self, user_id: uuid.UUID, run_id: str, body: RejectIn) -> RunRef:
        run = self._own(user_id, run_id)
        draft = self.repos.runs.latest_draft(user_id, run_id)
        try:
            run.reject_reasons = list(dict.fromkeys(body.reasons))
            run.reject_note = body.note
            self.repos.runs.stage_approval(
                Approval(
                    user_id=user_id,
                    run_id=run.id,
                    job_id=run.job_id,
                    decision="rejected",
                    reasons=run.reject_reasons,
                    edits_applied=bool(draft and draft.edited),
                    final=draft.tailored if draft else None,
                )
            )
            transition(self.repos, run, "rejected", commit=False)
            self.repos.session.commit()
        except AppError:
            self.repos.session.rollback()
            raise
        log.info(
            "run rejected user=%s run=%s reasons=%s", user_id, run.id, body.reasons
        )
        return RunRef(run_id=run.id, status=run.status)

    # --- regenerate / cancel -------------------------------------------------
    def regenerate(self, user_id: uuid.UUID, run_id: str, body: RegenerateIn) -> str:
        run = self._own(user_id, run_id)
        if run.status not in ("in_review", "rejected", "needs_attention"):
            raise IllegalTransition(
                f"A run that is {run.status} cannot be regenerated",
                details={"from": run.status, "to": "queued"},
            )
        guidance = None
        if body.guidance_from_rejection and (run.reject_reasons or run.reject_note):
            guidance = {
                "from_run": run.id,
                "reasons": run.reject_reasons,
                "note": run.reject_note,
            }
        # Same checks, cap and race handling as POST /jobs/{id}/tailor. It pins the
        # CURRENT approved profile, which may be newer than this run's.
        new_id = self.jobs.tailor(
            user_id,
            run.job_id,
            TailorIn(confirm_red_flags=body.confirm_red_flags),
            max_pages=body.max_pages,
            guidance=guidance,
        )
        if body.max_pages is not None:
            job = self.repos.jobs.get_for_user(user_id, run.job_id)
            if job is not None:
                job.max_pages_override = body.max_pages
                self.repos.session.commit()
        if run.status == "in_review":  # superseded: it can no longer be approved
            try:
                transition(
                    self.repos, run, "rejected", reason="regenerated", sync_job=False
                )
            except IllegalTransition:
                log.info("regenerate: old run %s already moved on", run.id)
        log.info("run regenerated user=%s from=%s new=%s", user_id, run.id, new_id)
        return new_id

    def cancel(self, user_id: uuid.UUID, run_id: str) -> RunRef:
        run = self._own(user_id, run_id)
        transition(self.repos, run, "cancelled", reason="user_cancelled")
        return RunRef(run_id=run.id, status=run.status)

    # --- pdf -----------------------------------------------------------------
    def pdf_url(self, user_id: uuid.UUID, run_id: str, which: str) -> str:
        run = self._own(user_id, run_id)
        if which == "approved":
            approval = self.repos.runs.approval_for(user_id, run_id)
            if (
                approval is None
                or approval.decision != "approved"
                or not approval.pdf_key
            ):
                raise NotFound("No approved PDF for this run")
            key, name = approval.pdf_key, approval.file_name or f"{run.id}.pdf"
        else:
            draft = self.repos.runs.latest_draft(user_id, run_id)
            if draft is None or not draft.pdf_key:
                raise NotFound("The PDF is not ready", code="pdf_not_ready")
            key, name = draft.pdf_key, f"draft-{run.id[:8]}.pdf"
        return signing.sign(key, min(settings.signed_url_ttl_s, 300), filename=name)
