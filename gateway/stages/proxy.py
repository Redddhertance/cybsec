# stage 7 - egress proxy / provider forwarding.
# repackages the scrubbed msgs into a provider-specific api req, sticks the llm provider's
# api key on, fires it off w a shared httpx client. raw assistant text goes back to the
# egress filter (stage 8). provider/transport failures -> 502 StageError (raised inside
# Provider.complete).

from __future__ import annotations

import httpx

from gateway.models import Message
from gateway.providers.base import Provider


async def forward(
    client: httpx.AsyncClient,
    provider: Provider,
    messages: list[Message],
    model: str,
    max_tokens: int,
) -> str:
    return await provider.complete(client, messages, model, max_tokens)
