"""Fake LLMs and builders for the tailoring-agent and screening tests."""

from app.agent.llm import Bullet, PlanOut, WriteOut
from app.agent.pipeline import Deps
from app.agent.tailor import AgentInput
from app.ai.embeddings import HashingEmbedder
from app.schemas.run import TailoredBullet
from tests.runs_helpers import JD, PROFILE


class FakeLLM:
    model = "fake-llm"

    def __init__(self, ask=None, writes=None, error=None):
        self.cost_usd = 0.0
        self.ask = ask or []
        self.writes = list(writes or [])  # WriteOut per write call; last one repeats
        self.error = error
        self.plan_calls, self.write_calls = [], []

    def plan(self, jd, bullets, skills, examples):
        if self.error:
            raise self.error
        self.plan_calls.append((bullets, skills, examples))
        return PlanOut(use_ids=[b.source_id for b in bullets], ask=self.ask)

    def write(self, jd, bullets, plan, skills, examples, feedback):
        self.write_calls.append((bullets, examples, feedback))
        self.cost_usd += 0.01
        if self.writes:
            i = min(len(self.write_calls) - 1, len(self.writes) - 1)
            return self.writes[i]
        return good_write(bullets)


def good_write(bullets: list[Bullet]) -> WriteOut:
    return WriteOut(
        summary="Backend engineer with Python and Postgres experience",
        bullets=[TailoredBullet(source_id=b.source_id, text=b.text) for b in bullets],
        skills_order=["Python", "Postgres"],
    )


def bad_write() -> WriteOut:
    return WriteOut(
        summary="Python expert who scaled Kubernetes to 10M users",
        bullets=[
            TailoredBullet(source_id="b1", text="Built Kafka pipelines at 9M events"),
            TailoredBullet(
                source_id="b2", text="Led the migration of Postgres to Aurora"
            ),
        ],
        skills_order=["Python", "Kubernetes"],
    )


def make_input(**over) -> AgentInput:
    events = over.pop("events", None)
    base = {
        "run_id": "run1",
        "jd": JD,
        "profile": PROFILE,
        "profile_version": 1,
        "answers": [],
        "max_pages": None,
        "guidance": None,
        "first_iteration": 1,
        "max_iterations": 3,
        "coverage_target": 0.6,
        "user_id": None,
        "progress": (lambda s, p: events.append((s, p)))
        if events is not None
        else None,
    }
    return AgentInput(**(base | over))


def make_deps(llm=None, **kw) -> Deps:
    return Deps(llm=llm or FakeLLM(), embedder=HashingEmbedder(), **kw)
