import logging
from typing import Protocol

log = logging.getLogger(__name__)


class IdentityProvider(Protocol):
    def revoke_sessions(self, sub: str) -> None: ...


class NoopIdentityProvider:
    """Access tokens are stateless, so we refuse tokens issued before a revocation
    ourselves (users.sessions_valid_after). TODO: also call the Auth0 Management API
    (revoke refresh tokens / end sessions) once M2M credentials are configured."""

    def revoke_sessions(self, sub: str) -> None:
        log.info("identity provider sessions not revoked: no management credentials")
