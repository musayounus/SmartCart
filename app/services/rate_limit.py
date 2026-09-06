import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings

try:  # pragma: no cover - exercised by whether redis is installed, not by a branch
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None


class InMemoryLimiter:
    """Fixed-window counter held in process memory.

    Correct for a single process and nothing more: two Fargate tasks would each
    allow the full limit. That is why the Redis backend exists. This one
    survives as the fallback so tests and a bare `uvicorn` run without needing
    Redis at all.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        recent = [t for t in self._hits[key] if t > cutoff]
        if len(recent) >= limit:
            retry_after = max(1, int(window_seconds - (now - recent[0])))
            recent.append(now)
            self._hits[key] = recent
            _reject(limit, window_seconds, retry_after)

        recent.append(now)
        self._hits[key] = recent

    async def reset(self) -> None:
        self._hits.clear()


class RedisLimiter:
    """Fixed-window counter shared across every task.

    INCR on a key whose name contains the window number, with EXPIRE set the
    first time that key is seen. Two round trips, no Lua, and no read-modify-
    write race: INCR is atomic, so concurrent tasks cannot both believe they
    were first.

    The window is derived from wall-clock time so every task computes the same
    bucket without coordinating.
    """

    def __init__(self, client: "Redis") -> None:
        self._redis = client

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        window = int(time.time()) // window_seconds
        redis_key = f"ratelimit:{key}:{window}"

        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, window_seconds)

        if count > limit:
            retry_after = window_seconds - (int(time.time()) % window_seconds)
            _reject(limit, window_seconds, max(1, retry_after))

    async def reset(self) -> None:
        await self._redis.flushdb()


def _reject(limit: int, window_seconds: int, retry_after: int) -> None:
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Rate limit exceeded: {limit} checkouts per {window_seconds}s",
        headers={"Retry-After": str(retry_after)},
    )


def _build_limiter() -> InMemoryLimiter | RedisLimiter:
    if settings.redis_url and Redis is not None:
        return RedisLimiter(Redis.from_url(settings.redis_url, decode_responses=True))
    return InMemoryLimiter()


limiter: InMemoryLimiter | RedisLimiter = _build_limiter()


async def enforce_checkout_rate_limit(request: Request) -> None:
    """Applied to the checkout route only.

    The limit is read from settings on every call rather than captured at
    import time, so tests can tighten it without restarting the app.
    """
    if settings.checkout_rate_limit <= 0:
        return

    client = request.client.host if request.client else "unknown"
    await limiter.check(client, settings.checkout_rate_limit, settings.checkout_rate_window_seconds)
