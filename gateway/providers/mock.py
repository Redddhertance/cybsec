# mock provider - runs the full pipeline w no api key or network.
# echoes the scrubbed user content back. importantly it leaves the placeholder tokens
# untouched so the egress un-redact stage can be tested end to end.

from __future__ import annotations

import httpx

from gateway.models import Message
from gateway.providers.base import Provider


class MockProvider(Provider):
    name = "mock"

    def build_request(self, messages, model, max_tokens):  # pragma: no cover - unused
        raise NotImplementedError("MockProvider does not make HTTP requests.")

    def parse_response(self, payload):  # pragma: no cover - unused
        raise NotImplementedError("MockProvider does not make HTTP requests.")

    async def complete(
        self,
        client: httpx.AsyncClient,
        messages: list[Message],
        model: str,
        max_tokens: int,
    ) -> str:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        return f"[mock-echo] {last_user}"
