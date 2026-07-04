# fastapi app - stage 1 (ingress) + the http surface.
# raw http body gets parsed by fastapi/pydantic into a GatewayRequest (stage 1), then handed
# to the orchestrator which runs stages 2-9. lifespan builds all the heavy shared stuff once
# at startup.

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway import pipeline
from gateway.config import get_settings
from gateway.models import ErrorResponse, GatewayRequest, GatewayResponse
from gateway.pipeline import GatewayContext
from gateway.providers import get_provider
from gateway.stages import StageError
from gateway.stages.audit import AuditLog
from gateway.stages.pii_ner import NerScrubber
from gateway.stages.ratelimit import RateLimiter
from gateway.stages.threatscan import ThreatScanner

logger = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    injection_scanner = ThreatScanner.from_file(settings.injection_signatures_path)
    internal_scanner = ThreatScanner.from_file(settings.internal_signatures_path)
    logger.info(
        "Loaded %d injection / %d internal signatures",
        injection_scanner.pattern_count,
        internal_scanner.pattern_count,
    )

    try:
        ner = NerScrubber(settings)
    except Exception as exc:  # pragma: no cover - env dependent
        # no spacy model? log it + carry on w stage 6 off rather than dying
        logger.warning("NER scrubber unavailable (%s); stage 6 disabled.", exc)
        ner = None

    limiter = RateLimiter(settings)
    provider = get_provider(settings)
    http = httpx.AsyncClient(timeout=settings.provider_timeout_s)
    audit = AuditLog(settings.audit_db_path)
    await audit.connect()

    app.state.ctx = GatewayContext(
        settings=settings,
        injection_scanner=injection_scanner,
        internal_scanner=internal_scanner,
        ner=ner,
        limiter=limiter,
        provider=provider,
        http=http,
        audit=audit,
    )
    try:
        yield
    finally:
        await http.aclose()
        await limiter.close()
        await audit.close()


app = FastAPI(title="LLM Security Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    ctx: GatewayContext = app.state.ctx
    return {
        "status": "ok",
        "injection_signatures": ctx.injection_scanner.pattern_count,
        "rate_limit_fallback": ctx.limiter.using_fallback,
        "provider": ctx.provider.name,
        "ner": ctx.ner is not None,
    }


@app.post("/v1/messages", response_model=GatewayResponse)
async def messages(request: GatewayRequest, http_request: Request):
    ctx: GatewayContext = app.state.ctx
    authorization = http_request.headers.get("authorization")
    client_ip = http_request.client.host if http_request.client else None
    try:
        return await pipeline.run(ctx, request, authorization, client_ip)
    except StageError as exc:
        body = ErrorResponse(
            request_id="",  # request_id is internal, leave it off rejected responses
            stage=exc.stage,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(),
            headers=exc.headers,
        )
