"""The contract between the `tailor` task and the tailoring agent.

The real agent is app/agent/graph.py (LangGraph) over app/agent/pipeline.py; tests
mostly use a fake.
It must call `fact_check` on everything it returns, and raise TransientError when the
LLM cannot be reached.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.schemas.run import Coverage, Pages, PendingQuestion, TailoredResume, Violation


@dataclass
class AgentInput:
    run_id: str
    jd: JobDescription
    profile: ProfileData  # the run's pinned approved version
    profile_version: int
    answers: list[tuple[str, str, str | None]]  # (skill, yes|no, detail)
    max_pages: int | None
    guidance: dict | None
    first_iteration: int  # numbering continues across a resume
    max_iterations: int
    coverage_target: float
    # Optional extras (defaults keep existing callers and fakes working).
    user_id: str | None = None
    # progress(step, payload): called at each step boundary; the task turns it into a
    # run event of type "step".
    progress: Callable[[str, dict], None] | None = None


@dataclass
class DraftResult:
    tailored: TailoredResume
    violations: list[Violation] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    pages: Pages = field(default_factory=Pages)
    outcome: str | None = None  # one line: what this iteration concluded


@dataclass
class AgentResult:
    questions: list[PendingQuestion] = field(default_factory=list)
    drafts: list[DraftResult] = field(default_factory=list)
    cost_usd: float = 0.0
    models: dict = field(default_factory=dict)
    prompt_version: str | None = None


class TailorAgent(Protocol):
    def run(self, inp: AgentInput, should_stop: Callable[[], bool]) -> AgentResult:
        """Return questions (nothing else) or one draft per iteration, best last.

        Poll `should_stop()` at step boundaries and return early when it is true.
        """
        ...
