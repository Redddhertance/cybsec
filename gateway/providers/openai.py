# openai chat completions adapter (works for openai-compatible apis too)

from __future__ import annotations

from gateway.providers.base import Provider

_DEFAULT_BASE = "https://api.openai.com"


class OpenAIProvider(Provider):
    name = "openai"

    def build_request(self, messages, model, max_tokens):
        base = self.settings.provider_base_url or _DEFAULT_BASE
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {
            "authorization": f"Bearer {self.settings.provider_api_key}",
            "content-type": "application/json",
        }
        return f"{base}/v1/chat/completions", headers, body

    def parse_response(self, payload: dict) -> str:
        choices = payload.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
