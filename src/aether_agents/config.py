"""Application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_host: str = Field(default="0.0.0.0", validation_alias="AETHER_API_HOST")
    api_port: int = Field(default=8000, validation_alias="AETHER_API_PORT")
    log_level: str = Field(default="INFO", validation_alias="AETHER_LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://aether:aether@localhost:5432/aether_agents",
        validation_alias="DATABASE_URL",
    )
    region: str = Field(default="delhi-nct", validation_alias="AETHER_REGION")
    worker_interval_seconds: int = Field(
        default=900,
        validation_alias="AETHER_WORKER_INTERVAL_SECONDS",
    )
    worker_pipeline_mode: str = Field(
        default="fixture",
        validation_alias="AETHER_WORKER_PIPELINE",
        description="fixture | live | off: science chain after each ingest tick",
    )

    data_gov_in_api_key: str = Field(default="", validation_alias="DATA_GOV_IN_API_KEY")
    openaq_api_key: str = Field(default="", validation_alias="OPENAQ_API_KEY")
    firms_map_key: str = Field(default="", validation_alias="FIRMS_MAP_KEY")
    llm_enabled: bool = Field(default=False, validation_alias="AETHER_LLM_ENABLED")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")


def get_settings() -> Settings:
    return Settings()
