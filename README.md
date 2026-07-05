# llm security gateway

security/privacy proxy that sits between clients and a third-party llm provider.
every request runs through a 9-stage pipeline. the heavy bit - matching prompts
against thousands of injection signatures - is a c++ aho-corasick engine wrapped
with pybind11. the fastapi app drives everything else.

## the pipeline

1. ingress / identity - fastapi + pydantic parse the raw body into a typed object
2. jwt auth - verify the sig, reject tampered/expired tokens (401)
3. rate limit - redis token bucket, in-mem fallback if redis is down (429)
4. threat scan - c++ aho-corasick vs the injection sigs (403 on a hit)
5. pii scrub, regex - emails, phones, ssns, cards, ips, street addresses
6. pii scrub, ner - spacy tags people / places / orgs and redacts them
7. egress proxy - httpx forwards the scrubbed prompt to the provider (502 on failure)
8. egress filter - re-scan the response for internal leaks, then un-redact the pii
9. audit - one sqlite row per transaction

pii gets swapped for reversible indexed placeholders (`[EMAIL_1]`, `[PERSON_2]`...).
the real value only lives in a per-request map and never leaves the box - stage 8
puts it back in the reply so the client still gets a sensible answer.

## setup

```bash
# installs deps + compiles the c++ engine (pip runs setup.py)
pip install -e ".[dev]"

# ner model for stage 6. md is a decent middle ground, sm is smaller/faster
python -m spacy download en_core_web_md

# optional - only needed for a shared/persistent rate limiter.
# without it the gateway just uses the in-mem bucket.
brew install redis && redis-server &
```

## running it

```bash
cp .env.example .env      # set GATEWAY_JWT_SECRET, provider, api key etc
python3 -m uvicorn gateway.app:app --port 8000
```

easiest way to poke at it is the little repl client (new terminal):

```bash
python3 scripts/chat.py
```

type a prompt, it prints the response + how many things got redacted. or hit it
with curl directly:

```bash
TOKEN=$(python3 scripts/mint_token.py)
curl -s localhost:8000/v1/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"messages":[{"role":"user","content":"my email is a@b.com, summarise"}]}'
```

defaults to the mock provider (echoes back, no api key needed). for a real llm set
`GATEWAY_PROVIDER=anthropic` (or `openai`) + `GATEWAY_PROVIDER_API_KEY` in `.env`.

note: the app wont boot on the default `GATEWAY_JWT_SECRET` - set a real one
(32+ bytes) in `.env` first, otherwise tokens would be forgeable.

## signatures

`signatures/injection_signatures.json` (ingress) and `internal_signatures.json`
(egress leaks) ship with a few placeholder patterns - swap in your own corpus.
each file is either a flat list of strings or a `{category: [strings]}` map.
matching is case-insensitive and everything gets flattened into one automaton at
startup. keys starting with `_` (like `_comment`) are ignored.

## tests

```bash
pytest -q
```

## layout

```
engine/             c++ aho-corasick automaton + pybind11 bindings -> ac_engine
gateway/            fastapi app, config, pipeline orchestrator
gateway/stages/     one module per stage
gateway/providers/  anthropic / openai / mock adapters
signatures/         placeholder sig dicts (replace these)
scripts/            mint_token.py + chat.py helpers
tests/              pytest suite
```
