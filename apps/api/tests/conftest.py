import contextlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.api.deps import get_session_factory
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.tasks.queue import RecordingQueue
from app.tasks.runtime import get_queue


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def queue():
    return RecordingQueue()


@pytest.fixture(autouse=True)
def overrides(db_session, tmp_path, monkeypatch, queue):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    monkeypatch.setattr(settings, "embedding_backend", "hashing")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_session_factory] = lambda: (
        lambda: contextlib.nullcontext(db_session)
    )
    yield
    app.dependency_overrides.clear()


from tests.apply_helpers import ats  # noqa: F401  (mock ATS fixture)
