# pipeline orchestrator - runs the 9 stages in order for one req.
# holds the shared process-wide stuff (scanners, ner model, rate limiter, provider, http
# client, audit log) in GatewayContext + threads a per-req RedactionMap + AuditRecord through
# the stages. any StageError short-circuits, an audit row always gets written in the finally.

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from gateway.config import Settings
from gateway.models import GatewayRequest, GatewayResponse, Message
from gateway.providers.base import Provider
from gateway.redaction import RedactionMap
from gateway.stages import StageError
from gateway.stages import proxy as proxy_stage
from gateway.stages.audit import AuditLog, AuditRecord
from gateway.stages.auth import authenticate
from gateway.stages.egress import filter_response
from gateway.stages.pii_ner import NerScrubber
from gateway.stages.pii_regex import scrub_regex
from gateway.stages.ratelimit import RateLimiter
from gateway.stages.threatscan import ThreatScanner


@dataclass
class GatewayContext:
    settings: Settings
    injection_scanner: ThreatScanner
    internal_scanner: ThreatScanner
    ner: NerScrubber | None
    limiter: RateLimiter
    provider: Provider
    http: httpx.AsyncClient
    audit: AuditLog


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scrub_message(msg: Message, ctx: GatewayContext, rmap: RedactionMap) -> Message:
    # regex (stage 5) then ner (stage 6) on one msg
    scrubbed = scrub_regex(msg.content, rmap)
    if ctx.ner is not None:
        scrubbed = ctx.ner.scrub(scrubbed, rmap)
    return Message(role=msg.role, content=scrubbed)


async def run(
    ctx: GatewayContext,
    request: GatewayRequest,
    authorization: str | None,
    client_ip: str | None,
) -> GatewayResponse:
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    rmap = RedactionMap()
    record = AuditRecord(request_id=request_id, ts=_now_iso(), client_ip=client_ip,
                         provider=ctx.provider.name)

    try:
        # stage 2 - identity / jwt
        user_id = authenticate(authorization, ctx.settings)
        record.user_id = user_id
        record.jwt_valid = True

        # stage 3 - rate limit
        try:
            await ctx.limiter.check(user_id)
        except StageError:
            record.rate_limited = True
            raise

        # stage 4 - ingress threat scan over all msg contents
        joined = "\n".join(m.content for m in request.messages)
        hits = ctx.injection_scanner.matches(joined)
        record.ingress_hits = len(hits)
        if hits:
            raise StageError("threatscan", 403,
                             "Request blocked: prohibited content detected.")

        # stages 5 & 6 - pii scrub (regex + ner)
        scrubbed = [_scrub_message(m, ctx, rmap) for m in request.messages]
        record.redaction_counts = rmap.counts_by_type()
        if ctx.settings.store_redacted_prompt:
            record.redacted_prompt = "\n".join(m.content for m in scrubbed)

        # stage 7 - egress proxy / fwd to provider
        model = request.model or ctx.settings.provider_model
        raw = await proxy_stage.forward(
            ctx.http, ctx.provider, scrubbed, model, request.max_tokens
        )

        # stage 8 - egress filter: leak scan + un-redact
        egress_leaks = ctx.internal_scanner.matches(raw)
        record.egress_hits = len(egress_leaks)
        final_text = filter_response(raw, rmap, ctx.internal_scanner)

        record.decision = "allowed"
        record.status_code = 200
        return GatewayResponse(
            request_id=request_id,
            model=model,
            content=final_text,
            redactions=rmap.total,
        )
    except StageError as exc:
        record.decision = "rejected"
        record.terminating_stage = exc.stage
        record.status_code = exc.status_code
        raise
    finally:
        record.latency_ms = (time.perf_counter() - started) * 1000.0
        # stage 9 - audit. dont let a logging fail hide the real outcome.
        try:
            await ctx.audit.write(record)
        except Exception:  # pragma: no cover - defensive
            pass
