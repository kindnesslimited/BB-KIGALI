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


# ---------- Server-side revocation (Apple guideline 5.1.1(v)) ----------
# Exchange the one-shot authorizationCode from Apple sign-in for a long-lived
# refresh_token, and revoke it when the user deletes their account.

APPLE_TOKEN_URL = f"{APPLE_ISSUER}/auth/token"
APPLE_REVOKE_URL = f"{APPLE_ISSUER}/auth/revoke"


def _load_apple_private_key() -> str | None:
    raw = os.environ.get("APPLE_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    # Support env vars that contain "\n" literals instead of real newlines.
    if "\\n" in raw and "\n" not in raw:
        raw = raw.replace("\\n", "\n")
    return raw


def apple_revocation_ready() -> bool:
    """Returns True iff all env vars needed to talk to Apple's token endpoint are set."""
    return all([
        os.environ.get("APPLE_TEAM_ID", "").strip(),
        os.environ.get("APPLE_KEY_ID", "").strip(),
        os.environ.get("APPLE_CLIENT_ID", "").strip(),
        _load_apple_private_key(),
    ])


def _make_apple_client_secret() -> str:
    team_id = os.environ["APPLE_TEAM_ID"].strip()
    key_id = os.environ["APPLE_KEY_ID"].strip()
    client_id = os.environ["APPLE_CLIENT_ID"].strip()
    private_key = _load_apple_private_key()
    assert private_key is not None
    now = int(time.time())
    return jwt.encode(
        {
            "iss": team_id,
            "iat": now,
            "exp": now + 60 * 60,
            "aud": APPLE_ISSUER,
            "sub": client_id,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "alg": "ES256"},
    )


async def exchange_code_for_refresh_token(authorization_code: str | None) -> str | None:
    """Exchange the one-shot authorizationCode returned by expo-apple-authentication
    for a long-lived refresh_token. Returns None if Apple keys aren't configured
    or Apple returns an error — this is best-effort and MUST NOT block sign-in."""
    if not authorization_code:
        return None
    if not apple_revocation_ready():
        logger.info("[apple-auth] APPLE_* env not set — skipping code exchange (revocation unavailable)")
        return None
    try:
        client_secret = _make_apple_client_secret()
        client_id = os.environ["APPLE_CLIENT_ID"].strip()
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(APPLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": authorization_code,
                "grant_type": "authorization_code",
            })
        if r.is_error:
            logger.warning("[apple-auth] token exchange failed: %s %s", r.status_code, r.text[:400])
            return None
        return (r.json() or {}).get("refresh_token")
    except Exception:
        logger.exception("[apple-auth] token exchange crashed")
        return None


async def revoke_apple_refresh_token(refresh_token: str | None) -> bool:
    """Revoke a stored refresh_token per Apple 5.1.1(v). Returns True on Apple 200,
    False otherwise. Never raises — account deletion must never be blocked by this."""
    if not refresh_token:
        return False
    if not apple_revocation_ready():
        logger.warning("[apple-auth] APPLE_* env not set — cannot call /auth/revoke")
        return False
    try:
        client_secret = _make_apple_client_secret()
        client_id = os.environ["APPLE_CLIENT_ID"].strip()
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(APPLE_REVOKE_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            })
        if r.status_code == 200:
            logger.info("[apple-auth] refresh token revoked")
            return True
        logger.warning("[apple-auth] revoke failed: %s %s", r.status_code, r.text[:400])
        return False
    except Exception:
        logger.exception("[apple-auth] revoke crashed")
        return False
