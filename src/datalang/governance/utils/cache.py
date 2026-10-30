import uuid
from fastapi import Request
from datetime import datetime, timezone

from governance.core.config import settings
from governance.schemas.cache import Cache, _caches
from governance.services.session import _sessions, _lock
from governance.error_handling.cache import CacheNotFoundError
from governance.error_handling.session import (
    SessionNotFoundError,
    SessionExpiredError,
    SessionOwnerMismatchError
)


def get_cache_id(request: Request, owner_id: str = "ABCUUID") -> uuid.UUID:
    session_id = request.cookies.get(settings.session_cookie)

    if not session_id:
        raise SessionNotFoundError()

    now = datetime.now(timezone.utc)

    with _lock:
        record = _sessions.get(session_id)

        if not record or now >= record["expires_at"]:
            _sessions.pop(session_id, None)
            raise SessionExpiredError()

        if record["owner"] != owner_id:
            raise SessionOwnerMismatchError()

        record["expires_at"] = now + settings.session_ttl
        return record["cache"]


def get_cache(cache_id: uuid.UUID) -> Cache | None:
    cache = _caches.get(cache_id)

    if cache is None:
        return None

    if datetime.now(timezone.utc) >= cache.expires_at:
        _caches.pop(cache_id, None)
        return None

    return cache


def handle_cache(request: Request) -> Cache:
    cache_id = get_cache_id(request)
    cache = get_cache(cache_id)

    if cache is None:
        raise CacheNotFoundError()

    return cache
