import json
import logging

import httpx
import pytest

from app.ai import backends, factory
from app.ai.errors import TransientError
from app.ai.local import (
    LocalClient,
    LocalJdExtractor,
    LocalProfileExtractor,
    LocalRejected,
)
from app.core.config import settings
from app.core.exceptions import ExtractionFailed, ExtractionUnavailable
from app.models.training import ExtractorShadowRun
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from tests.test_qwen import docx_bytes

RESUME = (
    "Jane Doe\nSenior Engineer at Acme\n- Built Kafka pipelines for billing\n"
    + "Skills: Kafka, Python\n" * 20
)
GOOD = ProfileData(
    contact=Contact(name="Jane Doe"),
    skills=["Kafka", "Python"],
    experience=[
        Experience(
            company="Acme", bullets=[Bullet(text="Built Kafka pipelines for billing")]
        )
    ],
)
BAD = GOOD.model_copy(update={"skills": ["Kafka", "Quantum"]})  # Quantum: invented
POSTING = "Backend Engineer at Acme in Bengaluru. Must know Kafka. " * 40


def client_for(handler):
    seen = []

    def wrapped(request):
        seen.append(json.loads(request.content))
        return handler(request)

    return LocalClient(
        "http://vllm.test", "m", 5, "key", transport=httpx.MockTransport(wrapped)
    ), seen


def ok(content: str):
    return lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": content}}]}
    )


# --- local extractors ---------------------------------------------------------
def test_request_uses_guided_json_and_auth():
    lc, seen = client_for(ok(GOOD.model_dump_json()))
    out = LocalProfileExtractor(lc).extract("r.docx", docx_bytes(RESUME))
    body = seen[0]
    assert "guided_json" in body and body["response_format"]["type"] == "json_schema"
    assert body["temperature"] == 0 and body["messages"][1]["content"] == (
        __import__("app.ai.extractor", fromlist=["docx_text"]).docx_text(
            docx_bytes(RESUME)
        )
    )
    assert out.contact.name == "Jane Doe"


def test_verbatim_violation_is_rejected_but_counted():
    lc, _ = client_for(ok(BAD.model_dump_json()))
    ex = LocalProfileExtractor(lc)
    with pytest.raises(LocalRejected):
        ex.extract("r.docx", docx_bytes(RESUME))
    detail = ex.extract_detailed("r.docx", docx_bytes(RESUME))
    assert detail.hallucinated == 1 and detail.dropped_fields == ["skills"]
    assert detail.checked.skills == ["Kafka"]


def test_schema_failure_is_rejected():
    lc, _ = client_for(ok('{"experience": "nope"}'))
    with pytest.raises(LocalRejected):
        LocalProfileExtractor(lc).extract("r.docx", docx_bytes(RESUME))
    assert (
        not LocalProfileExtractor(lc)
        .extract_detailed("r.docx", docx_bytes(RESUME))
        .schema_valid
    )


def test_http_errors_map_like_qwen():
    for handler, exc in (
        (lambda r: httpx.Response(503), TransientError),
        (lambda r: httpx.Response(400), ExtractionFailed),
    ):
        lc, _ = client_for(handler)
        with pytest.raises(exc):
            LocalJdExtractor(lc).extract(POSTING, None)

    def refuse(r):
        raise httpx.ConnectError("x")

    lc, _ = client_for(refuse)
    with pytest.raises(ExtractionUnavailable):
        LocalJdExtractor(lc).extract(POSTING, None)

    def slow(r):
        raise httpx.ReadTimeout("x")

    lc, _ = client_for(slow)
    with pytest.raises(TransientError):
        LocalJdExtractor(lc).extract(POSTING, None)


def test_jd_extractor_verbatim():
    jd = JobDescription(title="Backend Engineer", company="Acme", location="Mars")
    lc, _ = client_for(ok(jd.model_dump_json()))
    ex = LocalJdExtractor(lc)
    with pytest.raises(LocalRejected):
        ex.extract(POSTING, None)
    out = ex.extract_detailed(POSTING, None)
    assert out.checked.location is None and out.hallucinated == 1


# --- wrappers -------------------------------------------------------------------
class Fake:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def extract(self, *a):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_local_mode_uses_local_without_calling_claude():
    claude, local = Fake(GOOD), Fake(BAD.model_copy(update={"skills": ["Kafka"]}))
    out = backends.LocalFirstProfileExtractor(local, claude).extract("f", b"")
    assert out.skills == ["Kafka"] and claude.calls == 0


@pytest.mark.parametrize(
    "err", [TransientError("t"), LocalRejected(), ExtractionUnavailable()]
)
def test_local_mode_falls_back_to_claude(err):
    claude, local = Fake(GOOD), Fake(error=err)
    out = backends.LocalFirstProfileExtractor(local, claude).extract("f", b"")
    assert out is GOOD and claude.calls == 1
    jd = JobDescription(title="x")
    assert (
        backends.LocalFirstJdExtractor(Fake(error=err), Fake(jd)).extract("t", None)
        is jd
    )


def test_fallback_end_to_end_on_verbatim_failure():
    lc, _ = client_for(ok(BAD.model_dump_json()))
    claude = Fake(GOOD)
    ex = backends.LocalFirstProfileExtractor(LocalProfileExtractor(lc), claude)
    assert ex.extract("r.docx", docx_bytes(RESUME)) is GOOD


def test_shadow_returns_claude_and_logs_no_values(caplog):
    recorded = []
    lc, _ = client_for(ok(BAD.model_dump_json()))
    ex = backends.ShadowProfileExtractor(
        Fake(GOOD), LocalProfileExtractor(lc), lambda *a: recorded.append(a)
    )
    with caplog.at_level(logging.INFO):
        out = ex.extract("r.docx", docx_bytes(RESUME))
    assert out is GOOD
    kind, slice_, results = recorded[0]
    assert (kind, slice_) == ("profile", "docx") and results["schema_valid"]
    assert results["fields"]["skills"]["match"] is False
    assert results["fields"]["skills"]["fn"] == 1
    assert results["fields"]["contact.name"]["match"] is True
    assert results["hallucinated"] == 1
    blob = json.dumps(results) + caplog.text
    for value in ("Jane", "Kafka", "Quantum", "Acme", "billing"):
        assert value not in blob
    assert "skills=0" in caplog.text and "contact.name=1" in caplog.text


def test_shadow_survives_local_failure_and_recorder_failure():
    recorded = []
    ex = backends.ShadowJdExtractor(
        Fake(JobDescription(title="T")),
        Fake(error=TransientError("t")),
        lambda *a: recorded.append(a),
    )
    assert ex.extract(POSTING, "http://x").title == "T"
    assert recorded[0][2]["local_error"] is True and recorded[0][1].startswith("url:")

    def boom(*a):
        raise RuntimeError("db down")

    ex = backends.ShadowJdExtractor(
        Fake(JobDescription(title="T")), Fake(error=TransientError("t")), boom
    )
    assert ex.extract(POSTING, None).title == "T"


def test_shadow_db_recorder_persists_no_values(db_session, monkeypatch):
    import app.db.session as sess

    monkeypatch.setattr(sess, "SessionLocal", lambda: _Ctx(db_session))
    backends.db_recorder("jd", "text:short", {"schema_valid": True, "fields": {}})
    row = db_session.query(ExtractorShadowRun).one()
    assert row.kind == "jd" and not hasattr(row, "user_id")


class _Ctx:
    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *a):
        return False


# --- factory ----------------------------------------------------------------------
def test_unset_backend_keeps_ai_provider_behaviour(monkeypatch):
    monkeypatch.setattr(settings, "extractor_backend", None)
    monkeypatch.setattr(settings, "ai_provider", "qwen")
    assert type(factory.build_jd_extractor()).__name__ == "QwenJdExtractor"
    monkeypatch.setattr(settings, "ai_provider", "claude")
    assert type(factory.build_profile_extractor()).__name__ == "ClaudeVisionExtractor"


def test_backend_switching(monkeypatch):
    monkeypatch.setattr(settings, "local_extractor_url", "http://vllm.test")
    monkeypatch.setattr(settings, "ai_provider", "qwen")
    for mode, jd_cls, prof_cls in (
        ("claude", "ClaudeJdExtractor", "ClaudeVisionExtractor"),
        ("shadow", "ShadowJdExtractor", "ShadowProfileExtractor"),
        ("local", "LocalFirstJdExtractor", "LocalFirstProfileExtractor"),
    ):
        monkeypatch.setattr(settings, "extractor_backend", mode)
        assert type(factory.build_jd_extractor()).__name__ == jd_cls
        assert type(factory.build_profile_extractor()).__name__ == prof_cls


def test_local_without_url_degrades_to_claude(monkeypatch):
    monkeypatch.setattr(settings, "extractor_backend", "local")
    monkeypatch.setattr(settings, "local_extractor_url", "")
    assert type(factory.build_jd_extractor()).__name__ == "ClaudeJdExtractor"
