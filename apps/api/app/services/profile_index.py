import logging
import uuid

from app.ai.embeddings import Embedder
from app.models.profile import Profile, ProfileBullet
from app.repositories.manager import RepositoryManager

log = logging.getLogger(__name__)


def current_index(
    repos: RepositoryManager, embedder: Embedder, profile_id: str
) -> list[ProfileBullet]:
    """A profile's bullets, re-embedded if indexed with a different embedder.

    Vectors from different models are not comparable, so a changed embedding
    backend would otherwise silently return garbage for old approved profiles.
    """
    bullets = repos.profiles.bullets_for(profile_id)
    stale = [b for b in bullets if b.embedding_model != embedder.name]
    if stale:
        log.warning(
            "re-embedding stale bullets profile=%s stale=%d/%d embedder=%s",
            profile_id,
            len(stale),
            len(bullets),
            embedder.name,
        )
        vectors = embedder.embed_documents(
            [f"{b.entry_label}: {b.text}" for b in stale]
        )
        for b, vec in zip(stale, vectors, strict=True):
            b.embedding = vec
            b.embedding_model = embedder.name
        repos.profiles.update(stale[0])  # commits the whole session
    return bullets


def approved_with_index(
    repos: RepositoryManager, embedder: Embedder, user_id: uuid.UUID
) -> tuple[Profile, list[ProfileBullet]] | None:
    """The user's latest approved profile and its bullets; scoped by user_id."""
    profile = repos.profiles.get_latest_approved(user_id)
    if profile is None:
        log.debug("no approved profile user=%s", user_id)
        return None
    return profile, current_index(repos, embedder, profile.id)
