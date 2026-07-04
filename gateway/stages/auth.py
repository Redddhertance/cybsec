# stage 2 - jwt validation / identity.
# check the bearer token sig vs the configured secret/key. tampered or expired = fails
# verify = 401. the token's sub claim comes back as the user id we use downstream for
# rate limiting + audit.

from __future__ import annotations

import jwt

from gateway.config import Settings
from gateway.stages import StageError

_STAGE = "auth"


def authenticate(authorization_header: str | None, settings: Settings) -> str:
    # returns the user id (sub) or raises 401 via StageError
    if not authorization_header:
        raise StageError(_STAGE, 401, "Missing Authorization header.")

    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise StageError(_STAGE, 401, "Authorization header must be 'Bearer <token>'.")

    options = {"require": ["sub"]}
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise StageError(_STAGE, 401, "Token has expired.")
    except jwt.InvalidSignatureError:
        # sig doesnt match -> token was messed with
        raise StageError(_STAGE, 401, "Invalid token signature.")
    except jwt.InvalidTokenError as exc:
        # catch-all: DecodeError, missing claims, bad aud/iss etc
        raise StageError(_STAGE, 401, f"Invalid token: {exc}")

    sub = claims.get("sub")
    if not sub:
        raise StageError(_STAGE, 401, "Token missing 'sub' claim.")
    return str(sub)
