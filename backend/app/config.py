from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All app config. Fails fast at startup if a required var is missing —
    see .env.example for the full list and which sprint wires each one up."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Required now
    mongo_uri: str
    mistral_api_key: str

    # App
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:8000"]

    # Auth (Sprint 2)
    jwt_secret_key: str = ""

    # Vector store (Sprint 3)
    qdrant_url: str = "http://qdrant:6333"

    # LLM provider (Sprint 3 wires this up; declared now so the shape is stable)
    llm_provider: str = "groq"
    groq_api_key: str = ""
    anthropic_api_key: str = ""


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
