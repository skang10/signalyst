from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://signalyst:signalyst@localhost:5432/signalyst"
    redis_url: str = "redis://localhost:6379"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    agent_model: str = "gpt-5.5"
    agent_model_fast: str = "gpt-5.5-mini"
    # Per-token pricing in USD (update when actual rates are published)
    agent_model_input_cost_per_1k: float = 0.01
    agent_model_output_cost_per_1k: float = 0.03

    fred_api_key: str = ""
    eia_api_key: str = ""
    tabpfn_token: str = ""

    sentry_dsn: str = ""

    gpr_data_url: str = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
    gpr_cache_ttl_hours: int = 24

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
