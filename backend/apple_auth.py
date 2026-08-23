"""Sign in with Apple — verify identity token against Apple's JWKS."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import jwt
from jwt import algorithms as jwt_algorithms

logger = logging.getLogger(__name__)

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = f"{APPLE_ISSUER}/auth/keys"
APPLE_AUDIENCES = {a.strip() for a in os.environ.get("APPLE_AUDIENCES", "").split(",") if a.strip()}

_JWKS_CACHE: dict[str, Any] = {"keys": {}, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600  # Apple rotates rarely; re-fetch every hour.


async def _fetch_jwks() -> dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["keys"] and (now - _JWKS_CACHE["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE["keys"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(APPLE_JWKS_URL)
        r.raise_for_status()
        data = r.json()
    keys = {k["kid"]: k for k in data.get("keys", [])}
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["fetched_at"] = now
    return keys


async def verify_apple_identity_token(identity_token: str) -> dict[str, Any]:
    """Verify an Apple identity token (JWT signed RS256 against Apple JWKS).

    Returns the token claims dict on success.
    Raises ValueError with a user-friendly message on failure.
    """
    if not identity_token:
        raise ValueError("Missing identity token")
    if not APPLE_AUDIENCES:
        raise ValueError("APPLE_AUDIENCES not configured on the server")

    try:
        header = jwt.get_unverified_header(identity_token)
    except Exception as e:
        raise ValueError(f"Invalid identity token header: {e}")

    kid = header.get("kid")
    if not kid:
        raise ValueError("Identity token missing key id")

    keys = await _fetch_jwks()
    key_data = keys.get(kid)
    if not key_data:
        # Force refresh in case Apple rotated
        _JWKS_CACHE["fetched_at"] = 0
        keys = await _fetch_jwks()
        key_data = keys.get(kid)
    if not key_data:
        raise ValueError("Unknown Apple key id")

    public_key = jwt_algorithms.RSAAlgorithm.from_jwk(key_data)  # type: ignore[arg-type]

    last_err: Exception | None = None
    for aud in APPLE_AUDIENCES:
        try:
            claims = jwt.decode(
                identity_token,
                public_key,
                algorithms=["RS256"],
                audience=aud,
                issuer=APPLE_ISSUER,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
            return claims
        except jwt.InvalidAudienceError as e:
            last_err = e
            continue
        except Exception as e:
            raise ValueError(f"Apple token verification failed: {e}")
    raise ValueError(f"Apple token audience not accepted: {last_err}")
