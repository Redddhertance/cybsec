# mint a jwt for local testing, signed w the gateway's configured secret.
#   python scripts/mint_token.py                # user 'dev-user', 1h expiry
#   python scripts/mint_token.py --sub alice --ttl 3600
# prints the token to stdout so you can drop it straight into a curl:
#   curl -H "Authorization: Bearer $(python scripts/mint_token.py)" ...

from __future__ import annotations

import argparse
import time

import jwt

from gateway.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="mint a test jwt")
    parser.add_argument("--sub", default="dev-user", help="subject / user id claim")
    parser.add_argument("--ttl", type=int, default=3600, help="lifetime in secs")
    args = parser.parse_args()

    settings = get_settings()
    now = int(time.time())
    claims: dict = {"sub": args.sub, "iat": now, "exp": now + args.ttl}
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer

    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    print(token)


if __name__ == "__main__":
    main()
