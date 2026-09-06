import hashlib
import json
from typing import Any

from fastapi import Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

# Read endpoints that change slowly enough to hold briefly in a browser or CDN.
SHORT_CACHE = "public, max-age=60"

# Always revalidate, but allow a 304 when nothing changed. Used for the
# catalog: stock must never be served stale, or the concurrency demo shows
# numbers that are no longer true. An ETag still saves the payload without
# risking a stale answer.
REVALIDATE = "no-cache"


def _etag(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return f'"{hashlib.md5(encoded, usedforsecurity=False).hexdigest()}"'


def cached(request: Request, payload: Any, cache_control: str) -> Response:
    """Return payload with validators, or 304 if the client already has it.

    The ETag is computed from the serialised body, so any change to stock,
    price, or ordering produces a different tag. That is what makes it safe to
    pair an ETag with `no-cache` on the catalog: the client re-asks every time
    and only skips the download when the answer is genuinely identical.
    """
    tag = _etag(payload)
    headers = {"Cache-Control": cache_control, "ETag": tag}

    if request.headers.get("if-none-match") == tag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return JSONResponse(content=jsonable_encoder(payload), headers=headers)


def no_store(response: Response) -> None:
    """Router dependency marking every response as never cacheable.

    Applied to carts and orders: both are per-client and change on every
    write, so a shared cache holding either would leak one shopper's cart to
    another or serve an order list that is already wrong.
    """
    response.headers["Cache-Control"] = "no-store"
