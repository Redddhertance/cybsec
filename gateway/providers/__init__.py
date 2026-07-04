# llm provider adapters for the egress proxy (stage 7)

from gateway.config import Settings
from gateway.providers.base import Provider
from gateway.providers.anthropic import AnthropicProvider
from gateway.providers.openai import OpenAIProvider
from gateway.providers.mock import MockProvider

_REGISTRY: dict[str, type[Provider]] = {
    "mock": MockProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_provider(settings: Settings) -> Provider:
    try:
        cls = _REGISTRY[settings.provider.lower()]
    except KeyError:
        raise ValueError(
            f"Unknown provider {settings.provider!r}; expected one of {sorted(_REGISTRY)}"
        )
    return cls(settings)


__all__ = ["Provider", "get_provider"]
