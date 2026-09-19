from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROVIDER_KEY_FIELDS = {
    "groq": "groq_api_key",
    "mistral": "mistral_api_key",
    "anthropic": "anthropic_api_key",
    "bedrock": None,  # region-based, no API key
}


class Settings(BaseSettings):
    """All app config. Fails fast at startup if a required var is missing —
    see .env.example for the full list and which sprint wires each one up."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Always required, regardless of which LLM provider is selected
    mongo_uri: str
    jwt_secret_key: str

    # App
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:8000"]

    # Vector store (Sprint 3)
    qdrant_url: str = "http://qdrant:6333"

    # LLM provider — only the selected provider's key needs to be set; see
    # the validator below, which fails fast on whichever one is actually
    # missing rather than requiring every provider's key unconditionally.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_api_key: str = ""

    # Retrieval (Sprint 3)
    retrieval_k: int = 3
    retrieval_score_threshold: float = 0.5

    @model_validator(mode="after")
    def _require_selected_provider_key(self) -> "Settings":
        field = _PROVIDER_KEY_FIELDS.get(self.llm_provider)
        if field is not None and not getattr(self, field):
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider!r} but {field.upper()} is not set"
            )
        return self


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
