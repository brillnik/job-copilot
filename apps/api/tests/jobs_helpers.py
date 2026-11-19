"""Fakes and factories shared by the jobs tests. No real network or LLM."""

import contextlib

from app.ai.embeddings import HashingEmbedder
from app.ai.fetcher import FetchError
from app.ai.jd_extractor import finalise
from app.models.job import Job
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Education, Experience, ProfileData
from app.services.profile import ProfileService
from app.storage.local import LocalStorage
from app.tasks.jobs import TaskContext, scoring_config
from app.tasks.queue import RecordingQueue

LONG = "Backend Engineer at Acme in Bengaluru. " + "We build things. " * 40


class FakeExtractor:
    """Stands in for the LLM: returns `jd` run through the real verbatim check."""

    def __init__(self, jd: JobDescription | None = None, errors=()):
        self.jd = jd or JobDescription()
        self.errors = list(errors)
        self.calls: list[str] = []

    def extract(self, text, source_url):
        self.calls.append(text)
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        return finalise(self.jd, text, source_url)


class FakeTranscriber:
    def __init__(self, text=LONG):
        self.text, self.calls = text, 0

    def transcribe(self, data, media_type):
        self.calls += 1
        return self.text


class FakeFetcher:
    def __init__(self, pages=None, default=None):
        self.pages, self.default, self.calls = pages or {}, default, []

    def fetch(self, url):
        self.calls.append(url)
        page = self.pages.get(url, self.default)
        if isinstance(page, Exception):
            raise page
        if page is None:
            raise FetchError("not found")
        return page


class Boom:
    """Raises if anything calls it: proves a code path makes no LLM/network calls."""

    def __getattr__(self, name):
        raise AssertionError(f"unexpected call: {name}")


def make_ctx(db, tmp_path, **over) -> TaskContext:
    base = {
        "session_factory": lambda: contextlib.nullcontext(db),
        "storage": LocalStorage(tmp_path),
        "extractor": FakeExtractor(),
        "transcriber": FakeTranscriber(),
        "fetcher": FakeFetcher(),
        "embedder": HashingEmbedder(),
        "scoring": scoring_config(),
        "sleep": lambda s: None,
    }
    return TaskContext(**(base | over))


def make_user(db, sub="auth0|A") -> User:
    user = User(auth0_sub=sub, email=f"{sub}@x.co")
    db.add(user)
    db.commit()
    return user


PROFILE = ProfileData(
    contact=Contact(name="Ada", location="Bengaluru"),
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
    education=[Education(institution="IIT")],
)


def approve_profile(db, user, data: ProfileData = PROFILE, queue=None):
    repos = RepositoryManager(db)
    service = ProfileService(
        repos, None, None, HashingEmbedder(), queue or RecordingQueue()
    )
    service.save_draft(user.id, data)
    return service.approve(user.id)


def make_job(db, user, jd: JobDescription | None = None, **kw) -> Job:
    repos = RepositoryManager(db)
    fields = {"source": "text", "status": "new", "raw_text": LONG} | kw
    job = repos.jobs.add(Job(user_id=user.id, **fields))
    if jd is not None:
        repos.jobs.save_extraction(user.id, job.id, jd.model_dump(mode="json"), "test")
        db.commit()
    return job
