# runtime config, pulled from env vars / a .env file.
# all the knobs live here so the stages dont go poking at os.environ themselves.
# full list + defaults is in .env.example

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- stage 2: jwt auth ---
    jwt_secret: str = Field(default="dev-insecure-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_audience: str | None = Field(default=None)
    jwt_issuer: str | None = Field(default=None)

    # --- stage 3: rate limiting (token bucket) ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    rate_capacity: int = Field(default=20, description="max tokens = burst size")
    rate_refill_per_sec: float = Field(default=5.0, description="tokens added per sec")

    # --- stage 4 / 8: ac signature files ---
    injection_signatures_path: Path = Field(default=_ROOT / "signatures" / "injection_signatures.json")
    internal_signatures_path: Path = Field(default=_ROOT / "signatures" / "internal_signatures.json")

    # --- stage 6: spacy ner ---
    spacy_model: str = Field(default="en_core_web_sm")
    ner_labels: tuple[str, ...] = Field(default=("PERSON", "GPE", "LOC", "ORG"))

    # --- stage 7: provider / egress proxy ---
    provider: str = Field(default="mock", description="mock | anthropic | openai")
    provider_api_key: str = Field(default="")
    provider_base_url: str | None = Field(default=None, description="override provider base url")
    provider_model: str = Field(default="claude-3-5-sonnet-20241022")
    provider_timeout_s: float = Field(default=60.0)

    # --- stage 9: audit ---
    audit_db_path: Path = Field(default=_ROOT / "audit.db")
    store_redacted_prompt: bool = Field(
        default=False,
        description="if true, the scrubbed (pii-free) prompt gets stored in the audit log too",
    )


@lru_cache
def get_settings() -> Settings:
    # cached singleton so every stage sees the same config
    return Settings()
