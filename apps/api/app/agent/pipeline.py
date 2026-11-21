"""The tailoring steps as plain functions, and `run_pipeline`, the reference run.

Each node takes (ctx, state) and returns a dict of state updates; `state` holds only
JSON-able data so the LangGraph version (app/agent/graph.py) can checkpoint it. The
graph calls exactly these functions, so both produce the same drafts and the same
progress events.

Never invents facts: bullets come only from the run's pinned approved profile, and
every draft passes app/agent/fact_check.py. Logs carry ids and counts only.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent.examples import ExampleSource, examples_enabled_for
from app.agent.fact_check import _has_term, build_facts, fact_check
from app.agent.llm import (
    PROMPT_VERSION,
    Bullet,
    Example,
    PlanOut,
    TailorLLM,
    WriteOut,
)
from app.agent.pdf import layout, measure
from app.agent.tailor import AgentInput, AgentResult, DraftResult
from app.ai.embeddings import Embedder
from app.core.config import settings
from app.schemas.run import (
    Coverage,
    Pages,
    PendingQuestion,
    TailoredBullet,
    TailoredResume,
    Violation,
)

log = logging.getLogger(__name__)

STEPS = (
    "load_context",
    "rank_items",
    "plan",
    "write_draft",
    "fact_check",
    "coverage_and_render",
)
PER_QUERY, LIMIT, MAX_PER_ENTRY, MAX_QUESTIONS = 5, 15, 3, 3

State = dict[str, Any]


class Stopped(Exception):
    """The run was cancelled; raised at a step boundary."""


@dataclass
class Deps:
    llm: TailorLLM
    embedder: Embedder
    examples: ExampleSource | None = None
    synonyms: dict[str, list[str]] = field(
        default_factory=lambda: dict(settings.skill_synonyms)
    )


@dataclass
class Ctx:
    inp: AgentInput
    deps: Deps
    should_stop: Callable[[], bool] = lambda: False

    def step(self, name: str, **payload) -> None:
        if self.should_stop():
            raise Stopped
        if self.inp.progress:
            self.inp.progress(name, payload)

    def iteration(self, state: State) -> int:
        return self.inp.first_iteration + max(state.get("attempt", 1) - 1, 0)


def _entries(inp: AgentInput) -> list[tuple[str, str, list]]:
    rows = [
        (e.id, f"{e.company} {e.title or ''}".strip(), e.bullets)
        for e in inp.profile.experience
    ]
    rows += [(p.id, p.name, p.bullets) for p in inp.profile.projects]
    return rows


def _answered(state: State) -> set[str]:
    return {a[0].lower() for a in state["answers"]}


# --- nodes -------------------------------------------------------------------
def load_context(ctx: Ctx, state: State) -> State:
    ctx.step("load_context", iteration=ctx.inp.first_iteration)
    bullets = [
        {"source_id": b.id, "entry_id": eid, "label": label, "text": b.text}
        for eid, label, bs in _entries(ctx.inp)
        for b in bs
    ]
    return {
        "context": bullets,
        "attempt": 0,
        "drafts": [],
        "violations": [],
        "questions": [],
        "retry": False,
    }


def rank_items(ctx: Ctx, state: State) -> State:
    ctx.step("rank_items", iteration=ctx.inp.first_iteration)
    jd, emb = ctx.inp.jd, ctx.deps.embedder
    pool = state["context"]
    queries = [q.strip() for q in jd.must_have if q.strip()] or [
        q for q in [jd.title or "", *jd.responsibilities[:5]] if q.strip()
    ]
    best: dict[str, tuple[float, list[str]]] = {}
    if pool and queries:
        bvecs = emb.embed_documents([f"{b['label']}: {b['text']}" for b in pool])
        for q, qv in zip(queries, emb.embed_queries(queries), strict=True):
            scored = sorted(
                ((sum(x * y for x, y in zip(qv, v)), b) for v, b in zip(bvecs, pool)),
                key=lambda t: t[0],
                reverse=True,
            )
            for score, b in scored[:PER_QUERY]:
                if score < emb.min_score:
                    continue
                prev, hit = best.get(b["source_id"], (0.0, []))
                best[b["source_id"]] = (max(prev, score), [*hit, q])
    by_id = {b["source_id"]: b for b in pool}
    ranked, per_entry = [], {}
    for sid, (score, hit) in sorted(
        best.items(), key=lambda kv: (len(kv[1][1]), kv[1][0]), reverse=True
    ):
        b = by_id[sid]
        if per_entry.get(b["entry_id"], 0) >= MAX_PER_ENTRY:
            continue
        per_entry[b["entry_id"]] = per_entry.get(b["entry_id"], 0) + 1
        ranked.append({**b, "score": round(score, 4), "matched": hit})
        if len(ranked) >= LIMIT:
            break
    if not ranked:  # nothing matched: still tailor from real bullets, in order
        ranked = [{**b, "score": 0.0, "matched": []} for b in pool[:LIMIT]]
    return {"ranked": ranked}


def _bullets(state: State, ids: list[str] | None = None) -> list[Bullet]:
    rows = {r["source_id"]: r for r in state["ranked"]}
    keep = [rows[i] for i in ids if i in rows] if ids else list(rows.values())
    return [Bullet(r["source_id"], r["text"], r["label"], r["score"]) for r in keep]


def plan(ctx: Ctx, state: State) -> State:
    ctx.step("plan", iteration=ctx.inp.first_iteration)
    inp, deps = ctx.inp, ctx.deps
    examples: list[Example] = []
    if deps.examples is not None and examples_enabled_for(inp.user_id):
        examples = deps.examples.retrieve(str(inp.user_id), inp.jd)
    out = deps.llm.plan(inp.jd, _bullets(state), inp.profile.skills, examples)
    known = {r["source_id"] for r in state["ranked"]}
    use = [i for i in out.use_ids if i in known] or [
        r["source_id"] for r in state["ranked"]
    ]
    have = _answered(state) | {s.lower() for s in inp.profile.skills}
    ask = [s for s in dict.fromkeys(out.ask) if s.lower() not in have][:MAX_QUESTIONS]
    plan_out = out.model_copy(update={"use_ids": use, "ask": ask})
    return {
        "plan_out": plan_out.model_dump(),
        "examples": [e.__dict__ for e in examples],
        "questions": [PendingQuestion(skill=s).model_dump() for s in ask],
    }


def route_after_plan(state: State) -> str:
    return "ask_user" if state.get("questions") else "write_draft"


def write_draft(ctx: Ctx, state: State) -> State:
    attempt = state.get("attempt", 0) + 1
    ctx.step("write_draft", iteration=ctx.inp.first_iteration + attempt - 1)
    p = PlanOut.model_validate(state["plan_out"])
    feedback = [Violation.model_validate(v) for v in state.get("violations", [])]
    examples = [Example(**e) for e in state.get("examples", [])]
    out = ctx.deps.llm.write(
        ctx.inp.jd, _bullets(state, p.use_ids), p, ctx.inp.profile.skills,
        examples, feedback,
    )  # fmt: skip
    return {"attempt": attempt, "draft": out.model_dump()}


def _facts(ctx: Ctx, state: State):
    jd = ctx.inp.jd
    return build_facts(
        ctx.inp.profile,
        [tuple(a) for a in state["answers"]],
        extra_terms=[*jd.must_have, *jd.nice_to_have, *jd.keywords],
        synonyms=ctx.deps.synonyms,
    )


def _sanitise(facts, resume: TailoredResume, found: list[Violation]):
    """Last resort: fall back to profile text so nothing unsupported is kept."""
    bad = {v.source_id for v in found if v.field == "bullet"}
    fields = {v.field for v in found}
    bullets = [
        TailoredBullet(
            source_id=b.source_id,
            text=facts.bullets[b.source_id],
            reverted=True,
            revert_reason="unsupported_claim",
        )
        if b.source_id in bad and b.source_id in facts.bullets
        else b
        for b in resume.bullets
        if b.source_id in facts.bullets
    ]
    skills_bad = {v.term for v in found if v.field == "skills_order"}
    return resume.model_copy(
        update={
            "bullets": bullets,
            "summary": None if "summary" in fields else resume.summary,
            "cover_note": None if "cover_note" in fields else resume.cover_note,
            "skills_order": [s for s in resume.skills_order if s not in skills_bad],
        }
    )


def fact_check_node(ctx: Ctx, state: State) -> State:
    ctx.step("fact_check", iteration=ctx.iteration(state))
    facts = _facts(ctx, state)
    resume = WriteOut.model_validate(state["draft"]).to_resume()
    found = fact_check(facts, resume)
    note = None
    final = state["attempt"] >= ctx.inp.max_iterations
    if found and final:
        resume = _sanitise(facts, resume, found)
        note = f"reverted {len(found)} unsupported claim(s) to profile text"
        found = fact_check(facts, resume)
    return {
        "draft": resume.model_dump(),
        "violations": [v.model_dump() for v in found],
        "note": note,
        "retry": bool(found) and not final,
    }


def _coverage(ctx: Ctx, resume: TailoredResume) -> Coverage:
    must = ctx.inp.jd.must_have
    text = " ".join(
        [resume.summary or "", *resume.skills_order, *(b.text for b in resume.bullets)]
    )
    syn = ctx.deps.synonyms
    covered = []
    for m in must:
        low = m.lower()
        forms = {low, *(a.lower() for a in syn.get(low, []))}
        forms |= {c for c, al in ((k, [x.lower() for x in v]) for k, v in syn.items())
                  if low in al}  # fmt: skip
        if any(_has_term(text, f) for f in forms):
            covered.append(m)
    pct = len(covered) / len(must) if must else 1.0
    return Coverage(
        covered=covered,
        missing=[m for m in must if m not in covered],
        pct=round(pct, 2),
    )


def coverage_and_render(ctx: Ctx, state: State) -> State:
    ctx.step("coverage_and_render", iteration=ctx.iteration(state))
    resume = TailoredResume.model_validate(state["draft"])
    pages = measure(layout(ctx.inp.profile, resume))
    cap = ctx.inp.max_pages
    while cap is not None and pages.count > cap and len(resume.bullets) > 1:
        resume = resume.model_copy(update={"bullets": resume.bullets[:-1]})
        pages = measure(layout(ctx.inp.profile, resume))
    cov = _coverage(ctx, resume)
    viol = [Violation.model_validate(v) for v in state["violations"]]
    n = ctx.iteration(state)
    outcome = f"iteration {n}: coverage {cov.pct:.0%}, {len(viol)} violation(s)"
    if state.get("note"):
        outcome += f"; {state['note']}"
    draft = DraftResult(
        tailored=resume, violations=viol, coverage=cov, pages=pages, outcome=outcome
    )
    return {"drafts": [*state["drafts"], _dump(draft)]}


def route_after_render(state: State) -> str:
    return "write_draft" if state.get("retry") else "end"


# --- (de)serialising a DraftResult for the checkpointed state ------------------
def _dump(d: DraftResult) -> dict:
    return {
        "tailored": d.tailored.model_dump(),
        "violations": [v.model_dump() for v in d.violations],
        "coverage": d.coverage.model_dump(),
        "pages": d.pages.model_dump(),
        "outcome": d.outcome,
    }


def _load(d: dict) -> DraftResult:
    return DraftResult(
        tailored=TailoredResume.model_validate(d["tailored"]),
        violations=[Violation.model_validate(v) for v in d["violations"]],
        coverage=Coverage.model_validate(d["coverage"]),
        pages=Pages.model_validate(d["pages"]),
        outcome=d["outcome"],
    )


def initial_state(inp: AgentInput) -> State:
    return {"answers": [list(a) for a in inp.answers]}


def build_result(ctx: Ctx, state: State, cost_before: float) -> AgentResult:
    cost = max(ctx.deps.llm.cost_usd - cost_before, 0.0)
    models = {"tailor": ctx.deps.llm.model}
    if state.get("questions"):
        return AgentResult(
            questions=[PendingQuestion.model_validate(q) for q in state["questions"]],
            cost_usd=cost,
            models=models,
            prompt_version=PROMPT_VERSION,
        )
    return AgentResult(
        drafts=[_load(d) for d in state.get("drafts", [])],
        cost_usd=cost,
        models=models,
        prompt_version=PROMPT_VERSION,
    )


def run_pipeline(
    inp: AgentInput, deps: Deps, should_stop: Callable[[], bool] = lambda: False
) -> AgentResult:
    """The reference implementation: the six steps in order, retrying on violations."""
    ctx = Ctx(inp, deps, should_stop)
    before = deps.llm.cost_usd
    state = initial_state(inp)
    try:
        for node in (load_context, rank_items, plan):
            state |= node(ctx, state)
        if route_after_plan(state) == "ask_user":
            return build_result(ctx, state, before)
        while True:
            for node in (write_draft, fact_check_node, coverage_and_render):
                state |= node(ctx, state)
            if route_after_render(state) == "end":
                break
    except Stopped:
        return AgentResult()
    return build_result(ctx, state, before)
