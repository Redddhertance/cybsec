# provider interface: turn neutral msgs into a provider http req + parse the response
# back into plain text.

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from gateway.config import Settings
from gateway.models import Message
from gateway.stages import StageError

_STAGE = "proxy"


class Provider(ABC):
    name: str = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.provider_model

    @abstractmethod
    def build_request(
        self, messages: list[Message], model: str, max_tokens: int
    ) -> tuple[str, dict[str, str], dict]:
        # (url, headers, json_body) for the upstream POST
        ...

    @abstractmethod
    def parse_response(self, payload: dict) -> str:
        # pull the assistant text out of the provider's json
        ...

    async def complete(
        self,
        client: httpx.AsyncClient,
        messages: list[Message],
        model: str,
        max_tokens: int,
    ) -> str:
        # fwd the (already scrubbed) msgs upstream + return the text. remote
        # providers share this, the mock overrides it. any transport/http fail -> 502.
        url, headers, body = self.build_request(messages, model, max_tokens)
        try:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise StageError(_STAGE, 502, f"Upstream provider error: {exc.response.status_code}")
        except httpx.HTTPError as exc:
            raise StageError(_STAGE, 502, f"Upstream provider unreachable: {exc}")
        return self.parse_response(resp.json())
