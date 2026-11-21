"""Chooses the extraction backend (AI_PROVIDER=qwen|claude) in one place."""

import logging
from functools import lru_cache

from app.ai.backends import (
    LocalFirstJdExtractor,
    LocalFirstProfileExtractor,
    ShadowJdExtractor,
    ShadowProfileExtractor,
)
from app.ai.extractor import ClaudeVisionExtractor, ProfileExtractor
from app.ai.jd_extractor import (
    ClaudeImageTranscriber,
    ClaudeJdExtractor,
    ImageTranscriber,
    JdExtractor,
)
from app.ai.local import LocalClient, LocalJdExtractor, LocalProfileExtractor
from app.ai.qwen import (
    QwenClient,
    QwenImageTranscriber,
    QwenJdExtractor,
    QwenVisionExtractor,
)
from app.core.config import settings

log = logging.getLogger(__name__)


@lru_cache
def _qwen() -> QwenClient:
    # One shared HTTP client, so requests reuse connections to Ollama.
    return QwenClient(
        settings.qwen_base_url,
        settings.qwen_model,
        settings.qwen_timeout_s,
        settings.qwen_num_ctx,
    )


@lru_cache
def _local() -> LocalClient:
    return LocalClient(
        settings.local_extractor_url,
        settings.local_extractor_model,
        settings.local_extractor_timeout_s,
        settings.local_extractor_api_key,
    )


def _backend() -> str | None:
    """EXTRACTOR_BACKEND; None keeps the AI_PROVIDER behaviour. shadow/local without
    a LOCAL_EXTRACTOR_URL degrade to plain Claude rather than failing every call."""
    mode = settings.extractor_backend
    if mode in ("shadow", "local") and not settings.local_extractor_url:
        log.warning("EXTRACTOR_BACKEND=%s but LOCAL_EXTRACTOR_URL is empty", mode)
        return "claude"
    return mode


def _claude_profile() -> ProfileExtractor:
    return ClaudeVisionExtractor(settings.anthropic_api_key, settings.extraction_model)


def _claude_jd() -> JdExtractor:
    return ClaudeJdExtractor(settings.anthropic_api_key, settings.jd_extraction_model)


def build_profile_extractor() -> ProfileExtractor:
    mode = _backend()
    if mode == "claude":
        return _claude_profile()
    if mode == "shadow":
        return ShadowProfileExtractor(
            _claude_profile(), LocalProfileExtractor(_local())
        )
    if mode == "local":
        return LocalFirstProfileExtractor(
            LocalProfileExtractor(_local()), _claude_profile()
        )
    return _default_profile_extractor()


def build_jd_extractor() -> JdExtractor:
    mode = _backend()
    if mode == "claude":
        return _claude_jd()
    if mode == "shadow":
        return ShadowJdExtractor(_claude_jd(), LocalJdExtractor(_local()))
    if mode == "local":
        return LocalFirstJdExtractor(LocalJdExtractor(_local()), _claude_jd())
    return _default_jd_extractor()


def _default_profile_extractor() -> ProfileExtractor:
    if settings.ai_provider == "qwen":
        return QwenVisionExtractor(
            _qwen(), settings.qwen_max_pdf_pages, settings.qwen_pdf_scale
        )
    return ClaudeVisionExtractor(settings.anthropic_api_key, settings.extraction_model)


def _default_jd_extractor() -> JdExtractor:
    if settings.ai_provider == "qwen":
        return QwenJdExtractor(_qwen())
    return ClaudeJdExtractor(settings.anthropic_api_key, settings.jd_extraction_model)


def build_transcriber() -> ImageTranscriber:
    if settings.ai_provider == "qwen":
        return QwenImageTranscriber(_qwen())
    return ClaudeImageTranscriber(
        settings.anthropic_api_key, settings.jd_extraction_model
    )
