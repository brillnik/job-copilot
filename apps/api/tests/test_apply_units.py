"""Blocker detection, host policy, pre-submit check, mapping and the graph's
never-submit guarantee, all on fakes (no browser)."""

import pytest

from app.apply.blockers import detect_blockers
from app.apply.fields import ApprovedFile, FormField, Planned, ReadBack
from app.apply.graph import ApplyJob, run_graph
from app.apply.mapping import Mapper, classify, fit_option
from app.apply.policy import BlockedTarget, HostPolicy, check_target, extension_site
from app.apply.presubmit import presubmit_check
from app.core.config import settings
from app.schemas.profile import Contact, ProfileData
from app.storage.local import LocalStorage


class Frame:
    def __init__(self, url):
        self.url = url


class FakePage:
    def __init__(
        self, text="", html="", url="https://boards.greenhouse.io/a/1", frames=()
    ):
        self.text, self.html, self.url = text, html, url
        self.frames = [Frame(u) for u in frames]
        self.gotos = []

    def content(self):
        return self.html

    def inner_text(self, sel):
        return self.text

    def goto(self, url, **kw):
        self.gotos.append(url)

    def screenshot(self, **kw):
        return b"\x89PNG-fake"

    def wait_for_selector(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass

    def wait_for_load_state(self, *a):
        pass


# --- blockers ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kw", "kind"),
    [
        ({"frames": ["https://www.google.com/recaptcha/api2/anchor"]}, "captcha"),
        ({"frames": ["https://newassets.hcaptcha.com/captcha"]}, "captcha"),
        ({"html": '<div class="cf-turnstile"></div>'}, "captcha"),
        ({"html": '<div class="g-recaptcha" data-sitekey="k"></div>'}, "captcha"),
        ({"text": "Please sign in to apply"}, "login"),
        ({"html": '<input type="password">'}, "login"),
        ({"url": "https://x.test/login?next=/apply"}, "login"),
        ({"text": "Verify your email address"}, "verification"),
        ({"text": "Enter the code we sent to your phone"}, "verification"),
        ({"text": "Your OTP is required"}, "verification"),
        ({"text": "We detected unusual activity from your network"}, "bot_check"),
        ({"text": "Checking your browser before accessing"}, "bot_check"),
        ({"text": "Verify you are human"}, "bot_check"),
    ],
)
def test_every_blocker_kind_is_detected(kw, kind):
    b = detect_blockers(FakePage(**kw))
    assert b is not None and b.kind == kind


def test_a_normal_form_is_not_a_blocker():
    page = FakePage(text="Apply for Backend Engineer. First name. Last name. Email.")
    assert detect_blockers(page) is None


# --- policy --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://wellfound.com/jobs/1",
        "https://www.naukri.com/x",
        "https://hiring.cafe/a",
        "https://www.linkedin.com/jobs/view/1",
        "https://api.linkedin.com/x",
    ],
)
def test_denied_and_linkedin_hosts_are_refused_outright(url, monkeypatch):
    monkeypatch.setattr(settings, "apply_allow_private_hosts", True)
    with pytest.raises(BlockedTarget) as e:
        check_target(url)
    assert e.value.reason == "denied_site"
    with pytest.raises(BlockedTarget):
        HostPolicy.for_target(url)


def test_private_hosts_need_the_explicit_test_override(monkeypatch):
    monkeypatch.setattr(settings, "apply_allow_private_hosts", False)
    for url in (
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://10.0.0.5/x",
        "ftp://a.com/x",
    ):
        with pytest.raises(BlockedTarget):
            check_target(url)
    check_target("https://boards.greenhouse.io/acme/jobs/1")


def test_host_policy_allows_only_target_api_and_ats_suffixes(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://api.jobcopilot.test")
    p = HostPolicy.for_target("https://careers.acme.test/job/1")
    assert p.allows("https://careers.acme.test/x.js")
    assert p.allows("https://api.jobcopilot.test/files/t")
    assert p.allows("https://boards.greenhouse.io/acme")
    assert not p.allows("https://evil.test/pixel")
    assert not p.allows("https://www.google-analytics.com/c")
    assert not p.allows("https://wellfound.com/x") and not p.allows(
        "https://naukri.com"
    )
    assert not p.allows("http://127.0.0.1:8000/")
    assert (
        "MAP * ~NOTFOUND" in p.resolver_rules()
        and "EXCLUDE careers.acme.test" in p.resolver_rules()
    )


def test_extension_sites_are_never_playwright_targets():
    assert extension_site("https://wellfound.com/jobs/1") == "wellfound"
    assert extension_site("https://www.naukri.com/job") == "naukri"
    assert extension_site("https://hiring.cafe/jobs/9") == "hiring_cafe"
    assert extension_site("https://boards.greenhouse.io/a") is None


# --- mapping & pre-submit -------------------------------------------------------------
def test_classify_and_fit_option():
    f = lambda label, **kw: FormField("k", "#k", kw.pop("kind", "text"), label, **kw)
    assert classify(f("What is your notice period?")).field_type == "notice_period"
    assert classify(f("Expected CTC (LPA)")).field_type == "expected_ctc"
    y = classify(f("How many years of experience do you have with Python?"))
    assert (y.field_type, y.tool) == ("years_experience", "Python")
    assert classify(f("GitHub profile")).link_kind == "github"
    assert classify(f("Why us?", kind="textarea")).field_type == "open"
    sel = f("Auth", kind="select", options=["Yes, I am", "No"])
    assert fit_option("Yes", sel) == "Yes, I am" and fit_option("Maybe", sel) is None


class NoAnswers:
    def answer_for(self, *a, **k):
        return None


def approved(tmp_path):
    p = tmp_path / "cv.pdf"
    p.write_bytes(b"%PDF-1")
    return ApprovedFile(p, "cv.pdf", 6)


def test_mapper_never_invents_a_value(tmp_path):
    import uuid

    m = Mapper(
        uuid.uuid4(), NoAnswers(), ProfileData(contact=Contact(name="Ada Lovelace")),
        None, None, {}, approved(tmp_path),
    )  # fmt: skip
    fields = [
        FormField("first", "#f", "text", "First name", True),
        FormField("email", "#e", "email", "Email", True),  # no email anywhere
        FormField("why", "#w", "textarea", "Why us?", True),
        FormField("gender", "#g", "text", "Gender", False),
        FormField("cv", "#c", "file", "Resume", True),
        FormField("cover", "#cl", "file", "Cover letter", True),
    ]
    plan = {p.key: p for p in m.plan(fields)}
    assert plan["first"].value == "Ada" and plan["first"].source == "profile"
    assert plan["email"].value is None and plan["why"].value is None
    assert plan["gender"].value is None
    assert plan["cv"].source == "approved_pdf" and plan["cover"].value is None


def test_user_answers_win_and_must_fit_the_options(tmp_path):
    import uuid

    from app.services.screening import normalise

    m = Mapper(
        uuid.uuid4(), NoAnswers(), ProfileData(), None, None,
        {normalise("Authorized?"): "Yes", normalise("Pick one"): "Purple"}, approved(tmp_path),
    )  # fmt: skip
    a = FormField("a", "#a", "select", "Authorized?", True, options=["Yes", "No"])
    b = FormField("b", "#b", "select", "Pick one", True, options=["Red", "Blue"])
    pa, pb = m.plan([a, b])
    assert (pa.value, pa.source) == ("Yes", "user") and pb.value is None


def test_presubmit_blocks_missing_unsourced_and_wrong_files(tmp_path):
    ap = approved(tmp_path)
    fields = [
        FormField("n", "#n", "text", "Name", True),
        FormField("cv", "#cv", "file", "Resume", True),
    ]
    ok_plan = [
        Planned("n", "Name", True, "text", "Ada", "profile"),
        Planned("cv", "Resume", True, "file", ap.path, "approved_pdf"),
    ]
    ok_rb = {"n": ReadBack(value="Ada"), "cv": ReadBack(files=[("cv.pdf", 6)])}
    assert presubmit_check(fields, ok_plan, ok_rb, ap) == []
    # required without a value
    assert presubmit_check(fields, [ok_plan[1]], ok_rb, ap)[0] == "required_missing:n"
    # value from a source that is not allowed
    bad = [Planned("n", "Name", True, "text", "Ada", "guess"), ok_plan[1]]
    assert "source_not_allowed:n" in presubmit_check(fields, bad, ok_rb, ap)
    # the page holds a different file than the approved PDF
    for files in ([("other.pdf", 6)], [("cv.pdf", 7)], [("cv.pdf", 6), ("x.pdf", 1)]):
        rb = {**ok_rb, "cv": ReadBack(files=files)}
        assert "file_not_approved:cv" in presubmit_check(fields, ok_plan, rb, ap)
    # the page lost the value
    assert "required_empty:n" in presubmit_check(
        fields, ok_plan, {**ok_rb, "n": ReadBack()}, ap
    )
    # a non-resume field carrying the file
    ok_plan[0] = Planned("n", "Name", True, "text", "Ada", "profile")
    stray = [*fields, FormField("x", "#x", "file", "Other", False)]
    rb = {**ok_rb, "x": ReadBack(files=[("evil.pdf", 9)])}
    assert "file_not_approved:x" in presubmit_check(stray, ok_plan, rb, ap)


# --- graph: submit is unreachable unless everything checks out ---------------------------
class FakeAdapter:
    name = "greenhouse"
    uses_fallback = False

    def __init__(self, fields, readback=None, confirm=True):
        self.fields, self._rb, self._confirm = fields, readback, confirm
        self.submits = 0
        self.filled: dict = {}

    def matches(self, url, page):
        return True

    def prepare(self, page):
        pass

    def read_fields(self, page):
        return self.fields

    def fill(self, page, values, fields, pace):
        self.filled = dict(values)

    def read_back(self, page, fields):
        return self._rb if self._rb is not None else {
            f.key: ReadBack(value=str(self.filled.get(f.key, "")), checked=True,
                            files=[("cv.pdf", 6)] if f.kind == "file" and f.key in self.filled else [])
            for f in fields
        }  # fmt: skip

    def submit(self, page):
        self.submits += 1

    def confirmed(self, page):
        return self._confirm


def make_job(tmp_path, adapter, page=None, profile=None, provided=None):
    import uuid

    uid = uuid.uuid4()
    ap = approved(tmp_path)
    return ApplyJob(
        user_id=uid, application_id="app1", apply_url="https://boards.greenhouse.io/a/1",
        page=page or FakePage(text="Apply"), policy=HostPolicy("boards.greenhouse.io"),
        adapters=[adapter],
        mapper=Mapper(uid, NoAnswers(), profile or ProfileData(contact=Contact(name="Ada Lovelace", email="a@b.co")), None, None, provided or {}, ap),
        approved=ap, fallback=None, storage=LocalStorage(tmp_path), pace=lambda: None,
        should_stop=lambda: False, enabled_ats=["greenhouse"],
    )  # fmt: skip


FIELDS = [
    FormField("first", "#f", "text", "First name", True),
    FormField("cv", "#cv", "file", "Resume", True),
]


def test_clean_form_submits_once(tmp_path):
    ad = FakeAdapter(FIELDS)
    out = run_graph(make_job(tmp_path, ad))
    assert out.kind == "submitted" and ad.submits == 1


def test_required_field_without_value_never_reaches_submit(tmp_path):
    ad = FakeAdapter([*FIELDS, FormField("why", "#w", "textarea", "Why us?", True)])
    out = run_graph(make_job(tmp_path, ad))
    assert out.kind == "unmapped" and ad.submits == 0
    assert out.pending[0]["key"] == "why"


def test_wrong_file_in_the_form_never_reaches_submit(tmp_path):
    rb = {
        "first": ReadBack(value="Ada"),
        "cv": ReadBack(files=[("someone-elses.pdf", 6)]),
    }
    ad = FakeAdapter(FIELDS, readback=rb)
    out = run_graph(make_job(tmp_path, ad))
    assert (
        out.kind == "skipped" and out.reason.startswith("presubmit") and ad.submits == 0
    )


def test_blocker_on_any_page_never_reaches_submit(tmp_path):
    ad = FakeAdapter(FIELDS)
    out = run_graph(
        make_job(tmp_path, ad, page=FakePage(html='<div class="g-recaptcha">'))
    )
    assert out.kind == "blocked" and out.reason == "captcha" and ad.submits == 0


def test_cancel_before_submit_stops_the_run(tmp_path):
    ad = FakeAdapter(FIELDS)
    job = make_job(tmp_path, ad)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 6  # flips just before the submit node

    job.should_stop = stop
    out = run_graph(job)
    assert out.kind == "cancelled" and ad.submits == 0
