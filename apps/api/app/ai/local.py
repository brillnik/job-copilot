"""Fine-tuned local extractors behind an OpenAI-compatible endpoint (vLLM).

Same Extractor interfaces as the Claude/Qwen ones. Output is requested with guided
JSON (both `response_format: json_schema` and vLLM's `guided_json`), validated
against the Pydantic schema, then put through the existing verbatim check. Unlike
the Claude path, a verbatim violation is a *rejection* here (so `local` mode can
fall back to Claude) and is counted for the shadow report. Logs carry sizes and
timings only, never document text.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.errors import TransientError
from app.ai.extractor import MIN_SOURCE_CHARS, _Verbatim, docx_text, pdf_text
from app.ai.extractor import PROMPT as RESUME_PROMPT
from app.ai.jd_extractor import PROMPT as JD_PROMPT
from app.ai.jd_extractor import finalise, verify_verbatim
from app.ai.qwen import ollama_schema
from app.core.exceptions import ExtractionFailed, ExtractionUnavailable
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class LocalRejected(ExtractionFailed):
    """The local model's output failed schema or verbatim validation."""

    detail = "The local extractor's output was rejected"


@dataclass
class Outcome(Generic[M]):
    """What the local model produced. `raw` is None when the schema failed."""

    raw: M | None
    checked: M | None
    schema_valid: bool
    emitted: int = 0  # extracted text values (before the verbatim check)
    hallucinated: int = 0  # of those, how many the source did not contain
    dropped_fields: list[str] = field(default_factory=list)  # field names only


class LocalClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        api_key: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_s,
            headers=headers,
            transport=transport,
        )

    def chat(self, system: str, user: str, schema: dict, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": True},
            },
            "guided_json": schema,  # vLLM extension
        }
        started = time.perf_counter()
        try:
            response = self._http.post("/v1/chat/completions", json=payload)
        except httpx.ConnectError as e:
            log.error("local extractor unreachable")
            raise ExtractionUnavailable("The local extractor is not reachable") from e
        except httpx.TimeoutException as e:
            log.warning("local extractor timed out model=%s", self.model)
            raise TransientError("LocalTimeout") from e
        except httpx.HTTPError as e:
            log.warning("local extractor transport error=%s", type(e).__name__)
            raise TransientError(type(e).__name__) from e
        if response.status_code >= 500 or response.status_code == 429:
            log.warning("local extractor server error status=%d", response.status_code)
            raise TransientError(f"LocalHTTP{response.status_code}")
        if response.status_code >= 400:
            log.error(
                "local extractor rejected request status=%d", response.status_code
            )
            raise ExtractionFailed()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            log.error("local extractor returned an unreadable response")
            raise ExtractionFailed() from e
        if not content or not content.strip():
            raise LocalRejected()
        log.info(
            "local extractor call ok model=%s in %.1fs",
            self.model,
            time.perf_counter() - started,
        )
        return content

    def parse(
        self, model_cls: type[M], system: str, user: str, max_tokens: int
    ) -> M | None:
        """The validated model, or None if the output is not valid for the schema."""
        content = self.chat(system, user, ollama_schema(model_cls), max_tokens)
        try:
            return model_cls.model_validate_json(content)
        except ValidationError as e:
            log.error(
                "local output failed schema=%s errors=%d",
                model_cls.__name__,
                e.error_count(),
            )
            return None


# --- verbatim accounting ------------------------------------------------------
_SKIP_KEYS = ("id", "source_url", "start", "end", "work_mode")


def _flatten(v, key=None) -> list[str]:
    if isinstance(v, str):
        return [] if key in _SKIP_KEYS else [v]
    if isinstance(v, list):
        return [s for x in v for s in _flatten(x)]
    if isinstance(v, dict):
        return [s for k, x in v.items() for s in _flatten(x, k)]
    return []


def _strings(model: BaseModel) -> dict[str, list[str]]:
    """Field name -> every extracted text value, for counting what was dropped."""
    return {name: _flatten(value) for name, value in model.model_dump().items()}


def _account(raw: M, checked: M) -> tuple[int, int, list[str]]:
    before, after = _strings(raw), _strings(checked)
    emitted = sum(len(v) for v in before.values())
    dropped = [k for k in before if len(before[k]) > len(after.get(k, []))]
    lost = sum(len(before[k]) - len(after.get(k, [])) for k in before)
    # Numbers the verbatim check nulled out are also hallucinations.
    for k, v in raw.model_dump().items():
        if k.startswith(("experience_years", "ctc_lpa")) and v is not None:
            emitted += 1
            if getattr(checked, k) is None:
                lost += 1
                dropped.append(k)
    return emitted, lost, dropped


class LocalProfileExtractor:
    def __init__(self, client: LocalClient) -> None:
        self.client = client

    def extract_detailed(self, filename: str, data: bytes) -> Outcome[ProfileData]:
        is_pdf = data.startswith(b"%PDF-")
        source = pdf_text(data) if is_pdf else docx_text(data)
        if len(source) < MIN_SOURCE_CHARS:
            # The fine-tuned model reads text only; scans are Claude's job.
            raise LocalRejected("The resume has no usable text layer")
        raw = self.client.parse(ProfileData, RESUME_PROMPT, source, 8192)
        if raw is None:
            return Outcome(None, None, schema_valid=False)
        checked = _Verbatim(source).apply(raw)
        emitted, lost, fields = _account(raw, checked)
        return Outcome(raw, checked, True, emitted, lost, fields)

    def extract(self, filename: str, data: bytes) -> ProfileData:
        out = self.extract_detailed(filename, data)
        if not out.schema_valid or out.hallucinated:
            raise LocalRejected()
        return out.checked  # type: ignore[return-value]


class LocalJdExtractor:
    def __init__(self, client: LocalClient) -> None:
        self.client = client

    def extract_detailed(
        self, text: str, source_url: str | None
    ) -> Outcome[JobDescription]:
        raw = self.client.parse(JobDescription, JD_PROMPT, text, 4096)
        if raw is None:
            return Outcome(None, None, schema_valid=False)
        checked = verify_verbatim(raw, text)
        emitted, lost, fields = _account(raw, checked)
        return Outcome(
            raw, finalise(raw, text, source_url), True, emitted, lost, fields
        )

    def extract(self, text: str, source_url: str | None) -> JobDescription:
        out = self.extract_detailed(text, source_url)
        if not out.schema_valid or out.hallucinated:
            raise LocalRejected()
        return out.checked  # type: ignore[return-value]
