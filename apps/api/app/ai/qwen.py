"""Qwen3-VL extraction through a local Ollama server (native /api/chat).

Same contracts and post-checks as the Claude extractors: the model's output is
validated against the Pydantic schema and then stripped of anything the source
text does not contain. Logs carry model names, sizes and timings only, never
resume or posting text.
"""

import base64
import io
import logging
import re
import time
from typing import TypeVar

import httpx
import pypdfium2 as pdfium
from pydantic import BaseModel, ValidationError

from app.ai.errors import TransientError
from app.ai.extractor import (
    MIN_SOURCE_CHARS,
    _Verbatim,
    docx_text,
    pdf_text,
)
from app.ai.extractor import (
    PROMPT as RESUME_PROMPT,
)
from app.ai.jd_extractor import PROMPT as JD_PROMPT
from app.ai.jd_extractor import TRANSCRIBE_PROMPT, finalise
from app.core.exceptions import ExtractionFailed, ExtractionUnavailable
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


def ollama_schema(
    model_cls: type[BaseModel], non_null: frozenset[str] = frozenset()
) -> dict:
    """The model's JSON schema, flattened for Ollama's structured output.

    Ollama builds a grammar from the schema. With `$ref`s into `$defs` and optional
    fields it let the model skip whole sections (a resume came back with no
    experience at all), so references are inlined and every field is required.
    Pydantic still validates the result, and nullable fields stay nullable, except
    those named in `non_null`: constrained decoding made the model pick `null` for
    them even when the source states a value. The caller must treat "" as missing.
    """
    schema = model_cls.model_json_schema()
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            out = {}
            for key, value in node.items():
                if key in ("$defs", "title", "default"):
                    continue  # schema annotations, not fields
                if key == "properties":
                    # Keys here are field names, so a field called "title" must stay.
                    out[key] = {name: walk(sub) for name, sub in value.items()}
                else:
                    out[key] = walk(value)
            if out.get("type") == "object" and "properties" in out:
                # `id` fields are generated server-side; asking the model for them
                # only makes it invent hex strings.
                out["properties"].pop("id", None)
                for name in non_null & out["properties"].keys():
                    prop = out["properties"][name]
                    options = [
                        o for o in prop.get("anyOf", []) if o.get("type") != "null"
                    ]
                    if len(options) == 1:
                        out["properties"][name] = options[0]
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


class QwenClient:
    """Minimal Ollama chat client: one request, optional images, optional JSON schema."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        num_ctx: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self._http = httpx.Client(
            base_url=self.base_url, timeout=timeout_s, transport=transport
        )

    def chat(
        self,
        system: str,
        user: str,
        *,
        images: list[bytes] | None = None,
        schema: dict | None = None,
        max_tokens: int = 4096,
    ) -> str:
        # Instructions go in the system message and the untrusted document in the user
        # message, so text inside the document is never read as part of the prompt.
        message: dict = {"role": "user", "content": user}
        if images:
            message["images"] = [base64.b64encode(i).decode() for i in images]
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, message],
            # Ollama's default context is small and silently truncates long inputs.
            "options": {
                "temperature": 0,
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens,
            },
        }
        if schema is not None:
            payload["format"] = schema

        started = time.perf_counter()
        try:
            response = self._http.post("/api/chat", json=payload)
        except httpx.ConnectError as e:
            log.error("qwen unreachable url=%s", self.base_url)
            raise ExtractionUnavailable(
                "Qwen is not reachable. Start Ollama and pull the model."
            ) from e
        except httpx.TimeoutException as e:
            log.warning(
                "qwen timed out model=%s after %.0fs",
                self.model,
                time.perf_counter() - started,
            )
            raise TransientError("QwenTimeout") from e
        except httpx.HTTPError as e:
            log.warning("qwen transport error=%s", type(e).__name__)
            raise TransientError(type(e).__name__) from e

        if response.status_code == 404:
            log.error("qwen model missing model=%s (run: ollama pull)", self.model)
            raise ExtractionUnavailable(
                f"Model {self.model} is not installed in Ollama"
            )
        if response.status_code >= 500:
            log.warning("qwen server error status=%d", response.status_code)
            raise TransientError(f"QwenHTTP{response.status_code}")
        if response.status_code >= 400:
            log.error("qwen rejected request status=%d", response.status_code)
            raise ExtractionFailed()

        try:
            message = response.json()["message"]
            content = message["content"]
        except (ValueError, KeyError, TypeError) as e:
            log.error("qwen returned an unreadable response")
            raise ExtractionFailed() from e
        if not content.strip():
            # A thinking model that ran out of tokens while reasoning.
            log.error(
                "qwen returned empty content model=%s thinking=%s; "
                "use an -instruct model tag",
                self.model,
                bool(message.get("thinking")),
            )
            raise ExtractionFailed()
        log.info(
            "qwen call ok model=%s images=%d in %.1fs",
            self.model,
            len(images or []),
            time.perf_counter() - started,
        )
        return content

    def parse(
        self,
        model_cls: type[M],
        system: str,
        user: str,
        *,
        images: list[bytes] | None = None,
        max_tokens: int,
        non_null: frozenset[str] = frozenset(),
    ) -> M:
        content = self.chat(
            system,
            user,
            images=images,
            schema=ollama_schema(model_cls, non_null),
            max_tokens=max_tokens,
        )
        try:
            return model_cls.model_validate_json(content)
        except ValidationError as e:
            # Count and types only: error text would quote the model's output.
            log.error(
                "qwen output failed schema=%s errors=%d",
                model_cls.__name__,
                e.error_count(),
            )
            raise ExtractionFailed() from e


def pdf_page_images(data: bytes, max_pages: int, scale: float) -> list[bytes]:
    """Rasterise the first pages of a PDF to PNG; Qwen reads images, not PDFs."""
    images: list[bytes] = []
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise ExtractionFailed("Could not read the PDF file") from e
    try:
        for index in range(min(len(pdf), max_pages)):
            buf = io.BytesIO()
            pdf[index].render(scale=scale).to_pil().save(buf, format="PNG")
            images.append(buf.getvalue())
    except pdfium.PdfiumError as e:
        raise ExtractionFailed("Could not read the PDF file") from e
    finally:
        pdf.close()
    return images


# Appended to the shared resume prompt: a small model needs the field mapping spelled out
# (it left `title` null for headers like "Technical Lead — Acme Jul 2026 – Present").
RESUME_HINTS = (
    " For each experience entry, `title` is the job title or role and `company` is "
    "the employer. A header such as 'Technical Lead — Acme Corp Jul 2026 – Present | "
    "Delhi' means title='Technical Lead', company='Acme Corp', location='Delhi', "
    "start='2026-07', end='present'. Always fill `title` when a role is stated."
)

_MONTHS = {
    m: i
    for i, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for m in names
}
_MON_YEAR = re.compile(r"^([A-Za-z]{3,9})\.?,?\s+(\d{4})$")
_NUM_YEAR = re.compile(r"^(\d{1,2})[/-](\d{4})$")


def normalise_date(value: str | None) -> str | None:
    """'Jul 2026' -> '2026-07', 'Present' -> 'present'; anything else is kept as-is.

    The profile stores YYYY-MM (or 'present'); the experience-years scoring reads that.
    """
    if not value:
        return value
    v = value.strip()
    if v.lower() in ("present", "current", "now", "till date", "to date", "ongoing"):
        return "present"
    if m := _MON_YEAR.match(v):
        month = _MONTHS.get(m.group(1).lower())
        if month:
            return f"{m.group(2)}-{month:02d}"
    m = _NUM_YEAR.match(v)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    return v


def _normalise_dates(p: ProfileData) -> ProfileData:
    return p.model_copy(
        update={
            "experience": [
                e.model_copy(
                    update={
                        "start": normalise_date(e.start),
                        "end": normalise_date(e.end),
                    }
                )
                for e in p.experience
            ],
            "education": [
                e.model_copy(
                    update={
                        "start": normalise_date(e.start),
                        "end": normalise_date(e.end),
                    }
                )
                for e in p.education
            ],
        }
    )


class QwenVisionExtractor:
    """Resume to ProfileData. Text-layer resumes are sent as text; scans as page images."""

    def __init__(self, client: QwenClient, max_pages: int, scale: float) -> None:
        self.client = client
        self.max_pages = max_pages
        self.scale = scale

    def extract(self, filename: str, data: bytes) -> ProfileData:
        is_pdf = data.startswith(b"%PDF-")
        source_text = pdf_text(data) if is_pdf else docx_text(data)
        has_text = len(source_text) >= MIN_SOURCE_CHARS

        images = None
        if has_text or not is_pdf:
            user = source_text
        else:
            images = pdf_page_images(data, self.max_pages, self.scale)
            user = "The resume is in the attached page images."
            log.info("resume has no text layer; sending %d page images", len(images))

        try:
            parsed = self.client.parse(
                ProfileData,
                RESUME_PROMPT + RESUME_HINTS,
                user,
                images=images,
                max_tokens=8192,
                non_null=frozenset({"title"}),
            )
        except TransientError as e:
            raise ExtractionFailed("Extraction timed out; try again") from e
        parsed = _normalise_dates(parsed)
        return _Verbatim(source_text).apply(parsed) if has_text else parsed


class QwenJdExtractor:
    def __init__(self, client: QwenClient) -> None:
        self.client = client

    def extract(self, text: str, source_url: str | None) -> JobDescription:
        jd = self.client.parse(JobDescription, JD_PROMPT, text, max_tokens=4096)
        return finalise(jd, text, source_url)


class QwenImageTranscriber:
    def __init__(self, client: QwenClient) -> None:
        self.client = client

    def transcribe(self, data: bytes, media_type: str) -> str:
        return self.client.chat(
            TRANSCRIBE_PROMPT,
            "Transcribe the attached screenshot.",
            images=[data],
            max_tokens=4096,
        ).strip()
