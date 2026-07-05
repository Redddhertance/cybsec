# provider interface: turn neutral msgs into a provider http req + parse the response
# back into plain text.

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from gateway.config import Settings
from gateway.models import Message
from gateway.stages import StageError

_STAGE = "proxy"
_log = logging.getLogger("gateway.provider")


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
            # log the real status/url for ops, keep the client-facing detail generic
            # so we dont leak the upstream host in an error body
            _log.warning("provider %s returned %s", self.name, exc.response.status_code)
            raise StageError(_STAGE, 502, "Upstream provider error.")
        except httpx.HTTPError as exc:
            _log.warning("provider %s unreachable: %s", self.name, exc)
            raise StageError(_STAGE, 502, "Upstream provider unavailable.")
        return self.parse_response(resp.json())
