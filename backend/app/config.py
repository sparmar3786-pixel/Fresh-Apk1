from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    stale_data_seconds: int = 15
    engine_cycle_seconds: int = 5
    snapshot_poll_seconds: int = 20
    ai_cycle_seconds: int = 30
    openai_api_key: str | None = None
    openai_model: str = "gpt-5"
    # Signals-only provider; AI Chat remains on its existing route.
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4.1-mini"
    exa_api_key: str | None = None
    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    angel_api_key: str | None = None
    angel_client_code: str | None = None
    angel_pin: str | None = None
    angel_totp_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
