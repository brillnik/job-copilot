"""Factories and a fake tailoring agent for the runs/tracker/account tests."""

from app.agent.tailor import AgentInput, AgentResult, DraftResult
from app.ai.errors import TransientError
from app.core.clock import local_day
from app.models.job import AgentRun
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from app.schemas.run import (
    Coverage,
    Pages,
    PendingQuestion,
    TailoredBullet,
    TailoredResume,
)
from app.services.run_state import transition
from app.tasks import runs as run_tasks
from tests.jobs_helpers import approve_profile, make_ctx, make_job

PROFILE = ProfileData(
    contact=Contact(name="Ada Lovelace", location="Bengaluru"),
    skills=["Python", "Postgres"],
    experience=[
        Experience(
            id="e1",
            company="Acme",
            title="Engineer",
            start="2019-01",
            end="present",
            bullets=[
                Bullet(
                    id="b1", text="Built Kafka pipelines processing 2M events a day"
                ),
                Bullet(id="b2", text="Led the migration of Postgres to Aurora"),
            ],
        )
    ],
)

JD = JobDescription(
    company="Globex Corp", title="Backend Engineer", must_have=["Python"]
)


def tailored(**over) -> TailoredResume:
    base = {
        "summary": "Backend engineer with Python and Postgres experience",
        "bullets": [
            TailoredBullet(
                source_id="b1", text="Built Kafka pipelines handling 2M events a day"
            ),
            TailoredBullet(
                source_id="b2", text="Led the migration of Postgres to Aurora"
            ),
        ],
        "skills_order": ["Python", "Postgres"],
    }
    return TailoredResume(**(base | over))


def run_ready(db, tmp_path, user, *, status="in_review", render=True, job=None, **kw):
    """A job with an approved profile and a run moved to `status` the real way."""
    repos = RepositoryManager(db)
    profile = repos.profiles.get_latest_approved(user.id) or approve_profile(
        db, user, PROFILE
    )
    job = job or make_job(
        db, user, JD, company="Globex Corp", title="Backend Engineer", score=80
    )
    run = repos.jobs.reserve_run(user.id, job, profile.version, local_day(), 50, **kw)
    if status != "queued":
        transition(repos, run, "running")
    if status == "waiting_for_user":
        run.pending_questions = [{"skill": "Kubernetes", "prompt": None}]
        transition(repos, run, "waiting_for_user")
    elif status in ("in_review", "approved", "rejected"):
        db.add(
            run_tasks.Draft(
                run_id=run.id,
                user_id=user.id,
                iteration=1,
                tailored=tailored().model_dump(),
                coverage=Coverage(
                    covered=["Python"], missing=["Go"], pct=0.5
                ).model_dump(),
                pages=Pages(count=1, last_page_fill=0.4).model_dump(),
                outcome="first pass",
            )
        )
        run.iteration = 1
        transition(repos, run, "in_review")
        if render:
            run_tasks.render_pdf(make_ctx(db, tmp_path), user.id, run.id)
        if status in ("approved", "rejected"):
            transition(repos, run, status)
    elif status == "needs_attention":
        transition(repos, run, "needs_attention")
    elif status == "cancelled":
        transition(repos, run, "cancelled")
    return run


class FakeAgent:
    """Stands in for the tailoring agent; returns what the test configured."""

    def __init__(
        self, result: AgentResult | None = None, error: Exception | None = None
    ):
        self.result = result or AgentResult(
            drafts=[
                DraftResult(
                    tailored=tailored(),
                    coverage=Coverage(covered=["Python"], missing=[], pct=1.0),
                    pages=Pages(count=1, last_page_fill=0.5),
                    outcome="done",
                )
            ]
        )
        self.error, self.inputs = error, []
        self.on_run = None

    def run(self, inp: AgentInput, should_stop):
        self.inputs.append(inp)
        if self.on_run:
            self.on_run()
        if self.error:
            raise self.error
        return self.result


def ask(skill="Kubernetes") -> AgentResult:
    return AgentResult(questions=[PendingQuestion(skill=skill)])


unreachable = TransientError("llm down")
__all__ = ["AgentRun"]
