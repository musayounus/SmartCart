from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://smartcart:smartcart@localhost:5432/smartcart"

    # Checkouts allowed per client per window. The default is well above what
    # the concurrency tests burst (20), deliberately: a limit tight enough to
    # interfere would mask the oversell proof rather than break it visibly.
    # Set to 0 to disable.
    checkout_rate_limit: int = 60
    checkout_rate_window_seconds: int = 60

    # When set, the rate limiter counts in Redis so the limit is shared across
    # tasks. Unset falls back to per-process counting, which is only correct
    # for a single instance.
    redis_url: str = ""


settings = Settings()
