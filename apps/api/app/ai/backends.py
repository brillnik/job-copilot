"""EXTRACTOR_BACKEND wrappers: shadow (compare) and local (with Claude fallback)."""

import logging
from collections.abc import Callable
from typing import Any

from app.ai.errors import TransientError
from app.ai.extractor import ProfileExtractor
from app.ai.jd_extractor import JdExtractor
from app.ai.local import LocalJdExtractor, LocalProfileExtractor
from app.ai.shadow_diff import diff_results, log_line
from app.core.exceptions import ExtractionFailed, ExtractionUnavailable
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData

log = logging.getLogger(__name__)

# recorder(kind, slice, results) persists one comparison; failures are swallowed.
Recorder = Callable[[str, str, dict[str, Any]], None]

_FALLBACK_ON = (TransientError, ExtractionFailed, ExtractionUnavailable)


def profile_slice(filename: str, data: bytes) -> str:
    return "pdf" if data.startswith(b"%PDF-") else "docx"


def jd_slice(text: str, source_url: str | None) -> str:
    size = "short" if len(text) < 2000 else "medium" if len(text) < 8000 else "long"
    return f"{'url' if source_url else 'text'}:{size}"


def db_recorder(kind: str, slice_: str, results: dict[str, Any]) -> None:
    from app.db.session import SessionLocal
    from app.models.training import ExtractorShadowRun

    with SessionLocal() as session:
        session.add(ExtractorShadowRun(kind=kind, slice=slice_, results=results))
        session.commit()


def _record(recorder: Recorder, kind: str, slice_: str, results: dict) -> None:
    log.info("shadow diff kind=%s slice=%s %s", kind, slice_, log_line(results))
    try:
        recorder(kind, slice_, results)
    except Exception as e:  # noqa: BLE001 - shadowing must never break extraction
        log.error("shadow record failed error=%s", type(e).__name__)


class ShadowProfileExtractor:
    def __init__(
        self,
        primary: ProfileExtractor,
        local: LocalProfileExtractor,
        recorder: Recorder = db_recorder,
    ) -> None:
        self.primary, self.local, self.recorder = primary, local, recorder

    def extract(self, filename: str, data: bytes) -> ProfileData:
        result = self.primary.extract(filename, data)  # Claude's result is returned
        try:
            outcome = self.local.extract_detailed(filename, data)
            results = diff_results(result, outcome)
        except Exception as e:  # noqa: BLE001
            log.warning("shadow local failed error=%s", type(e).__name__)
            results = diff_results(result, None, local_error=True)
        _record(self.recorder, "profile", profile_slice(filename, data), results)
        return result


class ShadowJdExtractor:
    def __init__(
        self,
        primary: JdExtractor,
        local: LocalJdExtractor,
        recorder: Recorder = db_recorder,
    ) -> None:
        self.primary, self.local, self.recorder = primary, local, recorder

    def extract(self, text: str, source_url: str | None) -> JobDescription:
        result = self.primary.extract(text, source_url)
        try:
            outcome = self.local.extract_detailed(text, source_url)
            results = diff_results(result, outcome)
        except Exception as e:  # noqa: BLE001
            log.warning("shadow local failed error=%s", type(e).__name__)
            results = diff_results(result, None, local_error=True)
        _record(self.recorder, "jd", jd_slice(text, source_url), results)
        return result


class LocalFirstProfileExtractor:
    def __init__(self, local: ProfileExtractor, fallback: ProfileExtractor) -> None:
        self.local, self.fallback = local, fallback

    def extract(self, filename: str, data: bytes) -> ProfileData:
        try:
            return self.local.extract(filename, data)
        except _FALLBACK_ON as e:
            log.warning(
                "local extractor failed, using Claude error=%s", type(e).__name__
            )
            return self.fallback.extract(filename, data)


class LocalFirstJdExtractor:
    def __init__(self, local: JdExtractor, fallback: JdExtractor) -> None:
        self.local, self.fallback = local, fallback

    def extract(self, text: str, source_url: str | None) -> JobDescription:
        try:
            return self.local.extract(text, source_url)
        except _FALLBACK_ON as e:
            log.warning(
                "local extractor failed, using Claude error=%s", type(e).__name__
            )
            return self.fallback.extract(text, source_url)
