# anthropic messages api adapter

from __future__ import annotations

from gateway.models import Message
from gateway.providers.base import Provider

_DEFAULT_BASE = "https://api.anthropic.com"


class AnthropicProvider(Provider):
    name = "anthropic"

    def build_request(self, messages, model, max_tokens):
        base = self.settings.provider_base_url or _DEFAULT_BASE
        # anthropic wants the system prompt out-of-band, not as a msg
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        body: dict = {"model": model, "max_tokens": max_tokens, "messages": turns}
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self.settings.provider_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return f"{base}/v1/messages", headers, body

    def parse_response(self, payload: dict) -> str:
        blocks = payload.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
