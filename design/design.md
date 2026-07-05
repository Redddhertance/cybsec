# design notes

architecture + design record for the llm security gateway. covers the original brief,
how it's put together, the decisions made along the way, and what got reviewed before
it went public.

## the original brief

> _(paste your exact prompt here if you want it verbatim - summary of what was asked
> is below)_

build an llm security gateway: python for the gateway, an integrated c++ aho-corasick
engine for the fast pattern matching. requested pipeline:

1. ingress + identity - take the raw http request, parse the prompt into a python object with fastapi + pydantic
2. jwt validation - extract + verify the signature, reject tampered tokens with 401
3. rate limiting - redis token bucket keyed on user id, 429 if over
4. aho-corasick threat scan - c++ engine (pybind11 wrapper), compare the prompt against a json dictionary of known injection signatures
5. deterministic pii scrub - regex, redact emails / phones etc into placeholders before handing off to a third party
6. ner pii scrub - spacy nlp layer, tokenise + redact people / places
7. egress proxy - httpx repackages the (scrubbed) prompt into a new api request, attaches the llm api key, forwards it
8. egress filter - un-redact the response back to the original data, re-scan through aho-corasick to stop internal data leaking
9. audit - whole transaction written to sqlite for compliance

(the signature corpus itself is owned/supplied separately - the engine just loads + matches it.)

## architecture

one fastapi app orchestrates a 9-stage pipeline. every request runs the stages in order;
any stage can short-circuit with the right http status. the heavy bit (matching prompts
vs thousands of signatures) is a compiled c++ aho-corasick automaton exposed to python via
pybind11 as `ac_engine`.

    client ─▶ POST /v1/messages
               │
       1  ingress / parse         fastapi + pydantic
       2  jwt auth                verify sig, sub = user id        ─▶ 401
       3  rate limit              redis token bucket (+ fallback)  ─▶ 429
       4  threat scan             c++ aho-corasick vs injection sigs ─▶ 403
       5  pii scrub (regex)       email/phone/ssn/card/ip/address
       6  pii scrub (ner)         spacy people/places/orgs
       7  egress proxy            httpx ─▶ llm provider            ─▶ 502
       8  egress filter           leak scan + un-redact
       9  audit                   one sqlite row per txn
               │
    client ◀── GatewayResponse

### key design decisions

- **reversible pii redaction.** plain `[EMAIL]` tokens can't be put back, so every scrubbed
  value gets a unique indexed placeholder (`[EMAIL_1]`, `[PERSON_2]`...). a per-request map
  holds placeholder -> original. the real value never leaves the box; the llm only ever sees
  the placeholder. stage 8 swaps them back so the client still gets a coherent answer.
- **two signature sets, one engine.** ingress scans the prompt vs injection sigs (block = 403).
  egress scans the response vs internal-leak sigs (block = 502). both load into the same c++
  `Scanner` from separate json files.
- **c++ built with setuptools + pybind11**, not cmake - `pip install -e .` compiles it in one step.
- **redis token bucket with an in-memory fallback.** the real bucket lives in redis (atomic lua
  script, shared across workers). if redis is down the limiter quietly drops to a process-local
  bucket so dev/tests still run.
- **pluggable providers.** anthropic + openai adapters behind a common interface, plus a mock
  that echoes back so the whole pipeline runs with no api key or network.
- **privacy-preserving audit.** the log stores counts + decisions, not raw pii or prompts
  (opt-in flag to keep the scrubbed prompt for debugging). audit writes happen in a `finally`
  so they never mask the real outcome.

### stage -> http status

| stage | rejects with |
|-------|--------------|
| jwt auth | 401 |
| rate limit | 429 (+ Retry-After) |
| injection scan | 403 |
| provider / egress leak | 502 |

## what got reviewed before going public

### ai-text pass
went back through every file and rewrote comments/docstrings so they don't read as machine
-generated, then converted docstrings to `#` comments. swept the tree for the usual tells
(em/en dashes, "e.g."/"i.e.", capitalised full-sentence comments, boilerplate vocab). the only
remaining en-dash is a functional char inside the address regex.

### security review
manual review of the whole codebase, no real vulns found:

- **sql injection** - none, the audit insert is fully parameterised (`?` placeholders), table
  name is static.
- **jwt forgery** - `jwt.decode` pins `algorithms=[...]`, so the `alg:none` / algorithm-confusion
  forgery is blocked. `sub` is required.
- **dangerous calls** - no `eval`/`exec`/`pickle`/`shell=True`. the one `eval` is `redis.eval`
  running a static lua script with the key passed as a separate KEYS arg (no injection).
- **ssrf** - the provider url comes from config, never from user input.
- **tls / timeouts** - httpx verifies certs by default and a request timeout is set.
- **redos** - all pii regexes are bounded, no nested quantifiers.
- **committed secrets** - none. `.env`, `audit.db*` and `*.so` are gitignored (`.env.example`
  template is kept). the `AKIA` / `sk-live_` / `BEGIN RSA PRIVATE KEY` strings in the signature
  file are detection patterns, not real credentials.

### hardening applied
three fixes landed on top of the review:

1. **refuse to boot on the default jwt secret** - the app raises at startup if `GATEWAY_JWT_SECRET`
   is still the placeholder, so prod can't run with forgeable tokens.
2. **generic upstream errors** - provider failures log the real status/host for ops but return a
   generic 502 to the client, so the upstream host isn't leaked in an error body.
3. **minimal `/healthz`** - returns only `{"status":"ok"}`; provider name, signature count and
   rate-limit fallback state are no longer exposed on the unauthenticated endpoint.

### tests
20 pytest cases: c++ matcher (offsets, case-insensitivity, overlaps), jwt auth (valid / tampered
/ expired / missing), rate limit (bucket drain + per-user isolation), pii regex + un-redact
round-trip, and a full end-to-end pipeline run on the mock provider (happy path, injection 403,
bad token 401, audit row written). all green.

## known limitations / follow-ups

- the boot check is an exact match on the placeholder secret, so a weak custom secret still
  passes - a min-length check would be stronger.
- github secret-scanning may raise alerts on the detection patterns in the signature file;
  they're safe to dismiss.
- ner coverage is only as good as the spacy model (`en_core_web_md` default). org/place names
  it doesn't know slip through - a curated org override list or the transformer model would help.
- the signature dictionaries shipped here are tiny placeholders; the real corpus is supplied separately.
