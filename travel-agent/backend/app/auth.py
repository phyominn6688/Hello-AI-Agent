"""JWT authentication — validates Cognito (prod) or mock-auth (dev) tokens."""
import time
from functools import lru_cache
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch JWKS from auth provider. Cached — restarts on pod recycle."""
    resp = httpx.get(settings.auth_jwks_url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _get_public_key(kid: str):
    jwks = _fetch_jwks()
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return jwk.construct(key_data)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Public key not found for kid",
    )


def decode_token(token: str) -> dict:
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid", "")
        public_key = _get_public_key(kid)
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
    claims = decode_token(credentials.credentials)
    return CurrentUser(
        sub=claims.get("sub", ""),
        email=claims.get("email", ""),
        name=claims.get("name"),
    )
