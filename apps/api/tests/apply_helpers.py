"""Local mock ATS forms (127.0.0.1 only) and builders for the apply tests.

Nothing here touches the real internet: every page is served by a throwaway
http.server in a thread, and "submitting" only appends to `server.submissions`.
"""

import contextlib
import json
import threading
from email import message_from_bytes
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import HashingEmbedder
from app.apply.drivers import PlaywrightDriver
from app.apply.runner import ApplyContext
from app.core.security import token_claims
from app.main import app as fastapi_app
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from app.storage.local import LocalStorage
from tests.jobs_helpers import approve_profile, make_job
from tests.runs_helpers import run_ready

PROFILE = ProfileData(
    contact=Contact(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="+91 90000 00000",
        location="Bengaluru",
        links=["https://www.linkedin.com/in/ada", "https://github.com/ada"],
    ),
    skills=["Python", "Postgres"],
    experience=[
        Experience(
            id="e1", company="Acme", title="Engineer", start="2019-01", end="present",
            bullets=[
                Bullet(id="b1", text="Built Kafka pipelines processing 2M events a day"),
                Bullet(id="b2", text="Led the migration of Postgres to Aurora"),
            ],
        )
    ],
)  # fmt: skip
JD = JobDescription(
    company="Globex Corp", title="Backend Engineer", must_have=["Python"]
)


def fields_html(*, notice=True, extra="") -> str:
    return f"""
<label for="first_name">First Name *</label><input id="first_name" name="first_name" required aria-required="true"><br>
<label for="last_name">Last Name *</label><input id="last_name" name="last_name" required aria-required="true"><br>
<label for="email">Email *</label><input id="email" name="email" type="email" required><br>
<label for="phone">Phone</label><input id="phone" name="phone" type="tel"><br>
<label for="resume">Resume/CV *</label><input id="resume" name="resume" type="file" required><br>
<label for="linkedin">LinkedIn Profile</label><input id="linkedin" name="linkedin"><br>
{'<label for="notice">What is your notice period? *</label><input id="notice" name="notice" required><br>' if notice else ""}
{extra}"""


def gh_page(**kw) -> str:
    return (
        "<html><body><h1>Backend Engineer</h1>"
        '<form id="application_form" method="POST" action="/submit/greenhouse" enctype="multipart/form-data">'
        f'{fields_html(**kw)}<button id="submit_app" type="submit">Submit Application</button></form></body></html>'
    )


LEVER = """<html><body><h1>Backend Engineer</h1>
<form id="application-form" class="postings-form" method="POST" action="/submit/lever" enctype="multipart/form-data">
<label>Full name <input name="name" required></label><br>
<label>Email <input name="email" type="email" required></label><br>
<label>Phone <input name="phone" type="tel"></label><br>
<label>LinkedIn URL <input name="urls[LinkedIn]"></label><br>
<label>Resume/CV <input type="file" name="resume" required></label><br>
<label>Additional information <textarea name="comments"></textarea></label><br>
<button id="btn-submit" class="postings-btn" type="submit">Submit application</button></form></body></html>"""

ASHBY = """<html><body><div id="root"></div><script>
setTimeout(() => {
 document.getElementById('root').innerHTML = `<form id="f" class="ashby-application-form">
 <label for="_systemfield_name">Name</label><input id="_systemfield_name" name="_systemfield_name" required><br>
 <label for="_systemfield_email">Email</label><input id="_systemfield_email" name="_systemfield_email" type="email" required><br>
 <label for="_systemfield_resume">Resume</label><input id="_systemfield_resume" name="_systemfield_resume" type="file" required><br>
 <button type="submit">Submit Application</button></form>`;
 document.getElementById('f').addEventListener('submit', async (e) => {
   e.preventDefault();
   await fetch('/submit/ashby', {method: 'POST', body: new FormData(e.target)});
   document.body.innerHTML = '<h1>Your application was successfully submitted.</h1>';
 });
}, 150);
</script></body></html>"""

CAPTCHA = '<html><body><form id="application_form" method="POST" action="/submit/greenhouse"><input id="first_name" name="first_name"><div class="g-recaptcha" data-sitekey="x"></div><button type="submit">Submit</button></form></body></html>'
LOGIN = '<html><body><h1>Sign in to apply</h1><form><input name="u"><input type="password" name="p"><button>Log in</button></form></body></html>'
VERIFY = "<html><body><h1>Verify your email</h1><p>Enter the code we sent you.</p></body></html>"
BOTCHECK = "<html><body><h1>Unusual activity detected</h1><p>Please verify you are human.</p></body></html>"
NOFORM = (
    "<html><body><h1>Backend Engineer</h1><p>Apply by emailing us.</p></body></html>"
)
GENERIC = """<html><body><form method="POST" action="/submit/generic" enctype="multipart/form-data">
<label for="n">Your name *</label><input id="n" name="n" required>
<label for="e">E-mail *</label><input id="e" name="e" type="email" required>
<label for="cv">CV *</label><input id="cv" name="cv" type="file" required>
%s<button type="submit">Send</button></form></body></html>"""


class MockAts:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.submissions: list[dict] = []
        self.pages: dict[str, str] = {}
        self.redirects: dict[str, str] = {}
        self.confirm = True
        self.httpd: ThreadingHTTPServer | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def start(self) -> "MockAts":
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _send(self, body: str, code=200):
                data = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = self.path.split("?")[0]
                outer.requests.append(path)
                if path in outer.redirects:
                    self.send_response(302)
                    self.send_header("Location", outer.redirects[path])
                    self.end_headers()
                    return
                if path == "/confirmation":
                    return self._send("<h1>Thank you for applying</h1>")
                if path == "/thanks":
                    return self._send("<h1>Application submitted</h1>")
                if path in outer.pages:
                    return self._send(outer.pages[path])
                self._send("not found", 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n)
                outer.requests.append("POST " + self.path)
                ctype = self.headers.get("Content-Type", "")
                sub: dict = {"path": self.path, "fields": {}, "files": {}}
                if ctype.startswith("multipart/"):
                    msg = message_from_bytes(
                        b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body,
                        policy=HTTP,
                    )
                    for part in msg.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        fn = part.get_filename()
                        payload = part.get_payload(decode=True) or b""
                        if fn is not None:
                            sub["files"][name] = (fn, len(payload))
                        else:
                            sub["fields"][name] = payload.decode()
                outer.submissions.append(sub)
                if not outer.confirm:
                    return self._send("<h1>Working on it</h1>")
                if self.path == "/submit/ashby":
                    return self._send("ok")
                self.send_response(302)
                self.send_header(
                    "Location",
                    "/thanks" if self.path == "/submit/lever" else "/confirmation",
                )
                self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


def standard_pages(m: MockAts) -> MockAts:
    m.pages.update(
        {
            "/greenhouse/jobs/1": gh_page(),
            "/lever/co/1/apply": LEVER,
            "/ashby/co/1/application": ASHBY,
            "/captcha": CAPTCHA,
            "/login": LOGIN,
            "/verify": VERIFY,
            "/botcheck": BOTCHECK,
            "/noform": NOFORM,
            "/gh/open-question": gh_page(
                extra='<label for="why">Why do you want to work here? *</label><textarea id="why" name="why" required></textarea>'
            ),
            "/gh/work-auth": gh_page(
                extra='<label for="wa">Are you legally authorized to work in India? *</label>'
                '<select id="wa" name="wa" required><option value="">Select</option>'
                '<option value="y">Yes</option><option value="n">No</option></select>'
            ),
            "/gh/consent": gh_page(
                extra='<label><input type="checkbox" id="agree" name="agree" required> I agree to the privacy policy *</label>'
            ),
            "/generic/form": GENERIC % "",
            "/generic/quirky": GENERIC
            % '<label for="q">Favourite colour? *</label><input id="q" name="q" required>',
        }
    )
    m.redirects["/himalayas/apply/42"] = "/greenhouse/jobs/1"
    return m


@pytest.fixture
def ats():
    m = standard_pages(MockAts().start())
    yield m
    m.stop()


def _chrome_ok() -> str | None:
    import tempfile

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                tempfile.mkdtemp(), channel="chrome", headless=True
            )
            ctx.close()
        return None
    except Exception as e:  # noqa: BLE001
        return f"Chrome unavailable: {type(e).__name__}"


_CHROME: list = []


def chrome_skip_reason() -> str | None:
    if not _CHROME:
        _CHROME.append(_chrome_ok())
    return _CHROME[0]


needs_chrome = pytest.mark.skipif(
    chrome_skip_reason() is not None, reason=chrome_skip_reason() or ""
)


def make_apply_ctx(db, tmp_path, **over) -> ApplyContext:
    base = {
        "session_factory": lambda: contextlib.nullcontext(db),
        "storage": LocalStorage(tmp_path),
        "driver": PlaywrightDriver(
            "chrome", user_data_dir=str(tmp_path / "chrome"), headless=True
        ),
        "embedder": HashingEmbedder(),
        "sleep": lambda s: None,
    }
    return ApplyContext(**(base | over))


def api_as(sub: str) -> TestClient:
    fastapi_app.dependency_overrides[token_claims] = lambda: {"sub": sub}
    return TestClient(fastapi_app)


def approved_run(
    db, tmp_path, user, url: str, *, profile=PROFILE, prefs=None, job_kw=None
):
    """An approved run (with approved PDF) for a job whose apply link is `url`."""
    from app.repositories.manager import RepositoryManager

    if RepositoryManager(db).profiles.get_latest_approved(user.id) is None:
        approve_profile(db, user, profile)
    if prefs:
        user.preferences = prefs
        db.commit()
    job = make_job(
        db, user, JD, company="Globex Corp", title="Backend Engineer", score=80, url=url,
        **(job_kw or {}),
    )  # fmt: skip
    run = run_ready(db, tmp_path, user, job=job)
    client = api_as(user.auth0_sub)
    r = client.post(f"/runs/{run.id}/approve")
    assert r.status_code == 200, r.text
    return job, run


def enable_apply(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "apply_allow_private_hosts", True)
    monkeypatch.setattr(settings, "apply_nav_timeout_ms", 4000)


__all__ = ["json"]
