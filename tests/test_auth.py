# stage 2 - jwt auth tests

import time

import jwt
import pytest

from gateway.config import Settings
from gateway.stages import StageError
from gateway.stages.auth import authenticate


@pytest.fixture
def settings():
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


def _token(secret: str, **claims) -> str:
    base = {"sub": "user-1", "iat": int(time.time()), "exp": int(time.time()) + 60}
    base.update(claims)
    return jwt.encode(base, secret, algorithm="HS256")


def test_valid_token_returns_sub(settings):
    token = _token("test-secret")
    assert authenticate(f"Bearer {token}", settings) == "user-1"


def test_tampered_signature_rejected(settings):
    # signed w a diff secret -> sig verify fails (ie tampered)
    token = _token("attacker-secret")
    with pytest.raises(StageError) as exc:
        authenticate(f"Bearer {token}", settings)
    assert exc.value.status_code == 401


def test_expired_token_rejected(settings):
    token = _token("test-secret", exp=int(time.time()) - 10)
    with pytest.raises(StageError) as exc:
        authenticate(f"Bearer {token}", settings)
    assert exc.value.status_code == 401


def test_missing_header_rejected(settings):
    with pytest.raises(StageError) as exc:
        authenticate(None, settings)
    assert exc.value.status_code == 401


def test_malformed_scheme_rejected(settings):
    token = _token("test-secret")
    with pytest.raises(StageError):
        authenticate(token, settings)  # no "Bearer " prefix
