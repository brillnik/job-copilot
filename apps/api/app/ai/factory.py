"""Chooses the extraction backend (AI_PROVIDER=qwen|claude) in one place."""

from functools import lru_cache

from app.ai.extractor import ClaudeVisionExtractor, ProfileExtractor
from app.ai.jd_extractor import (
    ClaudeImageTranscriber,
    ClaudeJdExtractor,
    ImageTranscriber,
    JdExtractor,
)
from app.ai.qwen import (
    QwenClient,
    QwenImageTranscriber,
    QwenJdExtractor,
    QwenVisionExtractor,
)
from app.core.config import settings


@lru_cache
def _qwen() -> QwenClient:
    # One shared HTTP client, so requests reuse connections to Ollama.
    return QwenClient(
        settings.qwen_base_url,
        settings.qwen_model,
        settings.qwen_timeout_s,
        settings.qwen_num_ctx,
    )


def build_profile_extractor() -> ProfileExtractor:
    if settings.ai_provider == "qwen":
        return QwenVisionExtractor(
            _qwen(), settings.qwen_max_pdf_pages, settings.qwen_pdf_scale
        )
    return ClaudeVisionExtractor(settings.anthropic_api_key, settings.extraction_model)


def build_jd_extractor() -> JdExtractor:
    if settings.ai_provider == "qwen":
        return QwenJdExtractor(_qwen())
    return ClaudeJdExtractor(settings.anthropic_api_key, settings.jd_extraction_model)


def build_transcriber() -> ImageTranscriber:
    if settings.ai_provider == "qwen":
        return QwenImageTranscriber(_qwen())
    return ClaudeImageTranscriber(
        settings.anthropic_api_key, settings.jd_extraction_model
    )
