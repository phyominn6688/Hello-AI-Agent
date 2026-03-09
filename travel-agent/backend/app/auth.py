"""JWT authentication — validates Cognito (prod) or mock-auth (dev) tokens."""
import time
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=True)

# TTL-bounded JWKS cache — refreshed every 15 minutes so key rotations are picked up
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 900  # seconds


async def _fetch_jwks() -> dict:
    """Fetch JWKS from auth provider. Refreshed every 15 minutes."""
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(settings.auth_jwks_url)
        resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_fetched_at = now
    return _jwks_cache


def _get_public_key(kid: str, jwks: dict):
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return jwk.construct(key_data)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Public key not found for kid",
    )


async def decode_token(token: str) -> dict:
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid", "")
        jwks = await _fetch_jwks()
        public_key = _get_public_key(kid, jwks)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            options={"verify_at_hash": False},
        )
        if claims.get("exp", 0) < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
            )
        sub = claims.get("sub", "")
        email = claims.get("email", "")
        if not sub or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing required claims",
            )
        return claims
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


class CurrentUser:
    def __init__(self, sub: str, email: str, name: Optional[str] = None):
        self.sub = sub
        self.email = email
        self.name = name


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    claims = await decode_token(credentials.credentials)
    return CurrentUser(
        sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name"),
    )
