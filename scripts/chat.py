# interactive test client - type prompts, see what the gateway does w them.
# mints a jwt, pings /healthz to check the server's up, then sends each line you type as a
# user msg + prints the result.
#   python scripts/chat.py
#   python scripts/chat.py --url http://127.0.0.1:8000 --sub alice

from __future__ import annotations

import argparse
import sys
import time

import httpx
import jwt

from gateway.config import get_settings


def say(msg: str) -> None:
    print(msg, flush=True)


def mint(sub: str) -> str:
    s = get_settings()
    now = int(time.time())
    claims: dict = {"sub": sub, "iat": now, "exp": now + 3600}
    if s.jwt_audience:
        claims["aud"] = s.jwt_audience
    if s.jwt_issuer:
        claims["iss"] = s.jwt_issuer
    return jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm)


def main() -> None:
    ap = argparse.ArgumentParser(description="interactive gateway test client")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--sub", default="dev-user", help="jwt subject / user id")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    endpoint = f"{base}/v1/messages"
    healthz  = f"{base}/healthz"

    token   = mint(args.sub)
    headers = {"Authorization": f"Bearer {token}", "content-type": "application/json"}

    # 3s to connect (catches a wrong url fast), 120s to read (llms can be slow)
    timeout = httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=5.0)

    with httpx.Client(timeout=timeout) as client:

        # --- is the server even up ---
        try:
            h = client.get(healthz)
            info = h.json()
            say(f"server ok  provider={info.get('provider')}  "
                f"signatures={info.get('injection_signatures')}  "
                f"ner={info.get('ner')}  "
                f"rate-fallback={info.get('rate_limit_fallback')}")
        except Exception as exc:
            say(f"err: cant reach {healthz}: {exc}")
            say("is the server running?  python3 -m uvicorn gateway.app:app --port 8000")
            sys.exit(1)

        say(f"auth'd as {args.sub!r}  ->  {endpoint}")
        say("type a prompt + hit enter. empty line or ctrl-c to quit.\n")

        # --- chat loop ---
        while True:
            try:
                sys.stdout.write("you> ")
                sys.stdout.flush()
                prompt = sys.stdin.readline()
            except KeyboardInterrupt:
                say("")
                break

            if prompt is None or prompt.strip() == "":
                break
            prompt = prompt.strip()

            body = {"messages": [{"role": "user", "content": prompt}]}
            try:
                resp = client.post(endpoint, headers=headers, json=body)
            except httpx.ConnectError as exc:
                say(f"  [connection refused: {exc}]")
                continue
            except httpx.ReadTimeout:
                say("  [timed out - server took too long]")
                continue
            except httpx.HTTPError as exc:
                say(f"  [http error: {exc}]")
                continue
            except Exception as exc:
                say(f"  [unexpected err: {exc}]")
                continue

            # dump raw status so a non-200 is obvious even if json parse dies
            try:
                data = resp.json()
            except Exception:
                say(f"  [HTTP {resp.status_code}] raw: {resp.text[:500]}")
                continue

            say("")  # spacer before the reply
            if resp.status_code == 200:
                content    = data.get("content", "(no content in response)")
                redactions = data.get("redactions", "?")
                say(f"  gateway response:")
                say(f"  {content}")
                say(f"  [{redactions} redaction(s)]")
            else:
                stage  = data.get("stage", "unknown")
                detail = data.get("detail", str(data))
                say(f"  [BLOCKED]  stage={stage}  HTTP {resp.status_code}")
                say(f"  {detail}")
            say("")


if __name__ == "__main__":
    main()
