# pydantic schemas for the public api (stage 1 - ingress parsing).
# fastapi turns the raw http body into these typed objects + serialises responses back out.

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    # one chat msg, provider-neutral shape
    role: Literal["system", "user", "assistant"]
    content: str


class GatewayRequest(BaseModel):
    # inbound body for POST /v1/messages
    messages: list[Message] = Field(..., min_length=1)
    model: str | None = Field(
        default=None,
        description="optional model override, falls back to the configured default",
    )
    max_tokens: int = Field(default=1024, ge=1, le=32000)


class GatewayResponse(BaseModel):
    # what the client gets back after the full pipeline (pii un-redacted)
    request_id: str
    model: str
    content: str
    redactions: int = Field(description="how many pii spans got scrubbed before egress")


class ErrorResponse(BaseModel):
    # uniform error envelope for short-circuited reqs
    request_id: str
    stage: str
    detail: str
