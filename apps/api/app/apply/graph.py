"""The apply graph (LangGraph):

  load -> open -> detect_blockers -> read_fields -> map_values -> presubmit
       -> submit -> confirm -> proof

Any node can halt the run; a halted run goes straight to END with an Outcome and
`submit` is never reached. Only `submit` clicks the form's submit control, and it is
only reachable through `presubmit`. The graph holds no state between runs: a manual
application that waits for an answer is simply run again from `load`.
Logs carry ids and codes only: never field labels or values.
"""

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict
from urllib.parse import urljoin

from langgraph.graph import END, START, StateGraph

from app.apply import proof
from app.apply.adapters.base import FormAdapter
from app.apply.blockers import detect_blockers
from app.apply.fallback import FormFallback
from app.apply.fields import ALLOWED_SOURCES, ApprovedFile, FormField, Planned
from app.apply.mapping import Mapper, fit_option
from app.apply.policy import BlockedTarget, HostPolicy, check_target, host_of
from app.apply.presubmit import presubmit_check
from app.core.config import settings
from app.storage.base import Storage

log = logging.getLogger(__name__)


class Stopped(Exception):
    """The application was cancelled while the browser was running."""


@dataclass
class Outcome:
    kind: str  # submitted | blocked | unmapped | skipped | failed
    reason: str = ""
    pending: list[dict[str, Any]] = field(default_factory=list)


class AState(TypedDict, total=False):
    halt: bool


@dataclass
class ApplyJob:
    """Everything one browser run needs (inputs) and produces (outputs)."""

    user_id: Any
    application_id: str
    apply_url: str
    page: Any
    policy: HostPolicy
    adapters: list[FormAdapter]
    mapper: Mapper
    approved: ApprovedFile
    fallback: FormFallback | None
    storage: Storage
    pace: Callable[[], None]
    should_stop: Callable[[], bool]
    enabled_ats: list[str]
    # Called with the detected adapter name; a returned scope (e.g. "ats_hour") defers.
    on_detect: Callable[[str], str | None] | None = None
    # outputs
    adapter: FormAdapter | None = None
    fields: list[FormField] = field(default_factory=list)
    plan: list[Planned] = field(default_factory=list)
    shots: list[str] = field(default_factory=list)
    outcome: Outcome | None = None

    def halt(self, kind: str, reason: str, **kw: Any) -> AState:
        self.outcome = Outcome(kind, reason, **kw)
        log.info(
            "apply halt app=%s kind=%s reason=%s", self.application_id, kind, reason
        )
        return {"halt": True}

    def shot(self, name: str) -> None:
        png = self.page.screenshot(full_page=True)
        self.shots.append(
            proof.save_screenshot(
                self.storage, self.user_id, self.application_id, name, png
            )
        )


def _checked(job: ApplyJob) -> None:
    if job.should_stop():
        raise Stopped()


# --- nodes ----------------------------------------------------------------------
def load(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    try:
        check_target(job.apply_url)
    except BlockedTarget as e:
        return job.halt("skipped", e.reason)
    if not job.approved.path.exists():
        return job.halt("failed", "approved_pdf_missing")
    return {}


def _violation(job: ApplyJob) -> AState | None:
    if job.policy.violations:
        return job.halt("skipped", "host_not_allowed")
    return None


def _resolve(job: ApplyJob) -> str | AState:
    """Follow the apply link's redirects ONE hop at a time, checking each hop against
    the host policy before the browser goes anywhere (Chrome does not route redirect
    hops through our handler)."""
    url = job.apply_url
    for _ in range(6):
        try:
            resp = job.page.request.get(url, max_redirects=0, fail_on_status_code=False)
        except Exception:  # noqa: BLE001
            return job.halt("failed", "navigation_failed")
        loc = resp.headers.get("location")
        if not (300 <= resp.status < 400 and loc):
            return url
        url = urljoin(url, loc)
        if not job.policy.allows(url):
            job.policy.blocked.append(host_of(url))
            return job.halt("skipped", "host_not_allowed")
    return job.halt("skipped", "too_many_redirects")


def open_page(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    if hasattr(job.page, "on"):
        # Navigations only: blocked sub-resources are aborted by the route handler.
        job.page.on(
            "request",
            lambda r: job.policy.observe(r.url) if r.is_navigation_request() else None,
        )
    target = _resolve(job) if hasattr(job.page, "request") else job.apply_url
    if isinstance(target, dict):
        return target
    try:
        job.page.goto(target, wait_until="domcontentloaded")
    except Exception as e:  # noqa: BLE001
        if job.policy.blocked or job.policy.violations:
            return job.halt("skipped", "host_not_allowed")
        return job.halt("failed", f"navigation_failed:{type(e).__name__}")
    url = job.page.url
    if (
        url.startswith(("chrome-error:", "about:"))
        or not url
        or not job.policy.allows(url)
    ):
        if job.policy.blocked or job.policy.violations:
            return job.halt("skipped", "host_not_allowed")
        return job.halt("failed", "navigation_failed")
    job.pace()
    return _violation(job) or {}


def blockers_node(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    b = detect_blockers(job.page)
    if b:
        _try_shot(job, "blocked")
        return job.halt("blocked", b.reason)
    return {}


def _try_shot(job: ApplyJob, name: str) -> None:
    try:
        job.shot(name)
    except Exception:  # noqa: BLE001 - a missing screenshot must not hide the real reason
        log.info("apply screenshot failed app=%s", job.application_id)


def read_fields(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    page = job.page
    try:  # client-rendered forms (Ashby) appear a moment after the page loads
        page.wait_for_selector(
            "form, input", timeout=min(settings.apply_nav_timeout_ms // 4, 3000)
        )
    except Exception:  # noqa: BLE001 - no form at all: reported below
        log.info("apply no form appeared app=%s", job.application_id)
    adapter = next((a for a in job.adapters if a.matches(page.url, page)), None)
    if adapter is None:
        return job.halt("skipped", "unsupported_form")
    if adapter.name not in job.enabled_ats:
        return job.halt("skipped", "ats_disabled")
    if job.on_detect is not None:
        scope = job.on_detect(adapter.name)
        if scope:
            return job.halt("deferred", scope)
    job.adapter = adapter
    adapter.prepare(page)
    job.pace()
    b = detect_blockers(page)
    if b:
        _try_shot(job, "blocked")
        return job.halt("blocked", b.reason)
    if v := _violation(job):
        return v
    job.fields = adapter.read_fields(page)
    if not job.fields:
        return job.halt("blocked", "layout_change")
    return {}


def map_values(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    assert job.adapter is not None
    plan = job.mapper.plan(job.fields)
    missing = [p for p in plan if p.required and p.value is None]
    if missing and job.adapter.uses_fallback and job.fallback is not None:
        fp = job.fallback.propose(job.fields, plan)
        if not {f.key for f in job.fields} <= set(fp.intended):
            return job.halt("skipped", "fallback_incomplete")  # must list every field
        by_key = {p.key: p for p in plan}
        fields = {f.key: f for f in job.fields}
        for prop in fp.proposals:
            p = by_key.get(prop.key)
            if (
                p is None
                or p.value is not None
                or prop.confidence < settings.apply_fallback_min_confidence
                or prop.source not in ALLOWED_SOURCES - {"approved_pdf"}
                or not prop.value.strip()
            ):
                continue
            fitted = fit_option(prop.value, fields[prop.key])
            if fitted is not None:
                p.value, p.source, p.confidence = fitted, prop.source, prop.confidence
        missing = [p for p in plan if p.required and p.value is None]
    job.plan = plan
    if missing:
        fields = {f.key: f for f in job.fields}
        pending = [
            {
                "key": p.key,
                "label": p.label[:300],
                "kind": p.kind,
                "field_type": p.field_type,
                "options": fields[p.key].options,
            }
            for p in missing
        ]
        return job.halt("unmapped", "required_field_no_value", pending=pending)
    return {}


def presubmit(job: ApplyJob, state: AState) -> AState:
    _checked(job)
    assert job.adapter is not None
    values = {p.key: p.value for p in job.plan if p.value is not None}
    job.adapter.fill(job.page, values, job.fields, job.pace)
    b = detect_blockers(job.page)
    if b:
        _try_shot(job, "blocked")
        return job.halt("blocked", b.reason)
    if v := _violation(job):
        return v
    readback = job.adapter.read_back(job.page, job.fields)
    _try_shot(job, "filled")
    problems = presubmit_check(job.fields, job.plan, readback, job.approved)
    if problems:
        return job.halt("skipped", "presubmit:" + problems[0].split(":")[0])
    return {}


def submit(job: ApplyJob, state: AState) -> AState:
    _checked(job)  # last look at the cancel flag before the one irreversible click
    assert job.adapter is not None
    job.adapter.submit(job.page)
    job.pace()
    try:
        job.page.wait_for_load_state("domcontentloaded")
    except Exception:  # noqa: BLE001
        log.info("apply load state wait failed app=%s", job.application_id)
    return {}


def confirm(job: ApplyJob, state: AState) -> AState:
    assert job.adapter is not None
    waited = 0
    limit = settings.apply_nav_timeout_ms
    while True:
        if job.adapter.confirmed(job.page):
            return {}
        b = detect_blockers(job.page)
        if b:
            _try_shot(job, "blocked")
            return job.halt("blocked", b.reason)
        if waited >= limit:
            # We clicked submit and cannot tell: report failed, never retry blindly.
            _try_shot(job, "unconfirmed")
            return job.halt("failed", "unconfirmed_submit")
        job.page.wait_for_timeout(500)
        waited += 500


def proof_node(job: ApplyJob, state: AState) -> AState:
    _try_shot(job, "confirmation")
    job.outcome = Outcome("submitted")
    return {}


# --- wiring ---------------------------------------------------------------------
def _next(nxt: str):
    return lambda state: "end" if state.get("halt") else nxt


def build_apply_graph(job: ApplyJob):
    g = StateGraph(AState)
    order = [
        ("load", load),
        ("open", open_page),
        ("detect_blockers", blockers_node),
        ("read_fields", read_fields),
        ("map_values", map_values),
        ("presubmit", presubmit),
        ("submit", submit),
        ("confirm", confirm),
        ("proof", proof_node),
    ]
    for name, fn in order:
        g.add_node(name, lambda s, fn=fn: fn(job, s))
    g.add_edge(START, "load")
    for (name, _), (nxt, _) in itertools.pairwise(order):
        g.add_conditional_edges(name, _next(nxt), {nxt: nxt, "end": END})
    g.add_edge("proof", END)
    return g.compile()


def run_graph(job: ApplyJob) -> Outcome:
    """Run to completion; any crash becomes a failed Outcome (type name only)."""
    try:
        build_apply_graph(job).invoke({})
    except Stopped:
        job.outcome = Outcome("cancelled", "cancelled")
    except Exception as e:  # noqa: BLE001 - a task must never die silently
        log.error("apply crashed app=%s error=%s", job.application_id, type(e).__name__)
        job.outcome = Outcome("failed", f"browser_error:{type(e).__name__}")
    return job.outcome or Outcome("failed", "no_outcome")
