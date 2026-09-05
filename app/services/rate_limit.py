import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings


class FixedWindowLimiter:
    """Fixed-window request counter, keyed by client.

    In-memory and therefore per-process: two Fargate tasks would each allow the
    full limit. That is the honest limitation, and it is worth contrasting with
    the stock invariant, which lives in Postgres precisely so that it does not
    have this problem. Production would key this off Redis.

    Fixed window also allows a burst of up to 2x the limit across a window
    boundary. A sliding window or token bucket fixes that; neither is worth the
    extra machinery for a demo, and the limit here is a courtesy control rather
    than a security boundary.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        recent = [t for t in self._hits[key] if t > cutoff]
        if len(recent) >= limit:
            retry_after = max(1, int(window_seconds - (now - recent[0])))
            recent.append(now)
            self._hits[key] = recent
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded: {limit} checkouts per {window_seconds}s",
                headers={"Retry-After": str(retry_after)},
            )

        recent.append(now)
        self._hits[key] = recent

    def reset(self) -> None:
        self._hits.clear()


limiter = FixedWindowLimiter()


async def enforce_checkout_rate_limit(request: Request) -> None:
    """Applied to the checkout route only.

    The limit is read from settings on every call rather than captured at
    import time, so tests can tighten it without restarting the app.
    """
    if settings.checkout_rate_limit <= 0:
        return

    client = request.client.host if request.client else "unknown"
    limiter.check(client, settings.checkout_rate_limit, settings.checkout_rate_window_seconds)
