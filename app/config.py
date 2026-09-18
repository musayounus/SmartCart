from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://smartcart:smartcart@localhost:5432/smartcart"

    # Checkouts allowed per client per window. Deliberately well above what a
    # burst of concurrent checkouts costs: a limit tight enough to interfere
    # would mask the oversell proof rather than break it visibly, since a 429
    # reads as a successful rejection to an oversell assertion.
    #
    # Every shopper in a browser-driven race shares one client IP, so a single
    # run spends one unit per shopper. The UI caps a race at 40, so 100 keeps
    # any single race clear of the limit -- a 429 can never be mistaken for a
    # stock refusal mid-demo -- while a third rapid race inside the same window
    # does trip it, which is the only way to show the limiter working live.
    #
    # 60 was too low: two races reached it, so it masked the race it sits next
    # to. 240 was too high to demonstrate at all. Set to 0 to disable.
    checkout_rate_limit: int = 100
    checkout_rate_window_seconds: int = 60

    # When set, the rate limiter counts in Redis so the limit is shared across
    # tasks. Unset falls back to per-process counting, which is only correct
    # for a single instance.
    redis_url: str = ""


settings = Settings()
