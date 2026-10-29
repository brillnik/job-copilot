from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client() -> PyJWKClient:
    # Caches keys in-process; refetches when an unknown `kid` shows up.
    return PyJWKClient(f"https://{settings.auth0_domain}/.well-known/jwks.json")


def get_signing_key(token: str) -> Any:
    return _jwks_client().get_signing_key_from_jwt(token).key


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def token_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    """Validate an Auth0 access token and return its claims."""
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Auth0 is not configured"
        )
    if creds is None:
        raise _unauthorized("Missing bearer token")
    try:
        return jwt.decode(
            creds.credentials,
            get_signing_key(creds.credentials),
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise _unauthorized("Invalid token") from e


Claims = Annotated[dict[str, Any], Depends(token_claims)]
