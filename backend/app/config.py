from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    # NoDecode: without it, pydantic-settings tries to JSON-decode this
    # field's raw value itself (for *any* source -- a real .env file, a
    # real environment variable, not just the dotenv path) before
    # _split_comma_separated below ever runs, and raises SettingsError on
    # anything that isn't valid JSON -- which "http://localhost:8000" isn't.
    # Confirmed the hard way: this broke every test the moment a real .env
    # file existed on disk, even though a Settings(CORS_ORIGINS=[...]) call
    # with a Python list passed directly (bypassing both sources) had
    # masked it before.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:8000"]
    # False only for local docker-compose without Caddy's TLS in front —
    # a secure cookie is silently never sent back over plain HTTP.
    cookie_secure: bool = True

    # Compliance (Sprint 6). "production" turns on the guard in
    # _require_compliance_settings_in_production: the app refuses to start
    # without a named grievance officer and an on-VM security-log directory,
    # so a deployed instance can never silently ship placeholder values.
    environment: Literal["development", "production"] = "development"
    # DPDP Act 2023: a named grievance-officer contact, shown on /privacy.
    grievance_officer_name: str = ""
    grievance_officer_email: str = ""
    grievance_officer_address: str = ""
    # CERT-In Directions 2022: security events are written here, rotated
    # daily and kept 180 days, on the India-hosted VM only. Empty disables
    # the file sink (dev/tests); events still go to stdout.
    security_log_dir: str = ""
    # Chat turns auto-expire after this many days (Mongo TTL index), so the
    # retention period stated in the privacy notice is actually enforced.
    chat_retention_days: int = 365
    # How long database backups are kept (scripts/backup_mongo.sh reads the
    # same BACKUP_RETENTION_DAYS). A deleted account can survive in a backup
    # this long, and /privacy says so.
    backup_retention_days: int = 14

    # Vector store (Sprint 3)
    qdrant_url: str = "http://qdrant:6333"

    # LLM provider — only the selected provider's key needs to be set; see
    # the validator below, which fails fast on whichever one is actually
    # missing rather than requiring every provider's key unconditionally.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_api_key: str = ""

    # Retrieval (Sprint 3). k raised 3 -> 5 in Sprint 5 (D066): a narrative
    # fact pattern can genuinely touch more than one offence (e.g. cheating
    # *and* criminal breach of trust), and the system prompt's narrative
    # guidance asks the model to surface every section that applies, not
    # just the single closest match -- k=3 was too narrow to give it that
    # choice even when the right sections were being retrieved at all.
    retrieval_k: int = 5
    retrieval_score_threshold: float = 0.5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """.env.example documents CORS_ORIGINS as a bare comma-separated
        string (CORS_ORIGINS=http://a,http://b), but pydantic-settings'
        default env parsing for a list field expects JSON syntax and raises
        SettingsError on anything else — reproduced directly, not assumed.
        A real list (e.g. constructed in tests) passes through unchanged."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_selected_provider_key(self) -> "Settings":
        field = _PROVIDER_KEY_FIELDS.get(self.llm_provider)
        if field is not None and not getattr(self, field):
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider!r} but {field.upper()} is not set"
            )
        return self

    @model_validator(mode="after")
    def _require_compliance_settings_in_production(self) -> "Settings":
        if self.environment == "production":
            required = (
                "grievance_officer_name",
                "grievance_officer_email",
                "grievance_officer_address",
                "security_log_dir",
            )
            missing = [f.upper() for f in required if not getattr(self, f)]
            if missing:
                raise ValueError(
                    f"ENVIRONMENT=production but {', '.join(missing)} not set "
                    "(DPDP grievance officer + CERT-In log directory are mandatory)"
                )
        return self


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
