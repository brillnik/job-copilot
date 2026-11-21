"""Builds the tailoring agent from settings (TAILOR_AGENT=none|graph)."""

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.agent.examples import DbExampleSource
from app.agent.graph import GraphTailorAgent
from app.agent.llm import ClaudeTailorLLM
from app.agent.pipeline import Deps
from app.agent.tailor import TailorAgent
from app.ai.embeddings import Embedder
from app.core.config import settings


def build_tailor_agent(
    session_factory: Callable[[], AbstractContextManager[Session]],
    embedder: Embedder,
) -> TailorAgent | None:
    if settings.tailor_agent != "graph":
        return None
    deps = Deps(
        llm=ClaudeTailorLLM(settings.anthropic_api_key, settings.tailor_model),
        embedder=embedder,
        examples=DbExampleSource(session_factory, embedder),
    )
    return GraphTailorAgent(deps, path=settings.tailor_checkpoint_path)
