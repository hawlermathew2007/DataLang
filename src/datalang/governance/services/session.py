from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import RLock
from fastapi import HTTPException, Request, Response

from governance.core.config import settings
from governance.schemas.cache import Cache

# Use Redis or another shared store in production
# Protect from CSRF too and clear session after done
_sessions = {}
_lock = RLock()


def create_app_session(response: Response, cache: Cache):
    session_id = token_urlsafe(32)

    with _lock:
        _sessions[session_id] = {
            "cache": cache.id,
            "owner": cache.owner_id,
            "expires_at": datetime.now(timezone.utc) + settings.session_ttl,
        }

    response.set_cookie(
        key=settings.session_cookie,
        value=session_id,
        httponly=True,
        secure=True,       # HTTPS only
        samesite="lax",
        max_age=int(settings.session_ttl.total_seconds()),
        path="/",
    )


def get_cache_id(request: Request, owner_id: str = "ABCUUID"):
    session_id = request.cookies.get(settings.session_cookie)

    if not session_id:
        raise HTTPException(401, "Please connect to a database first.")

    now = datetime.now(timezone.utc)

    with _lock:
        record = _sessions.get(session_id)

        if not record or now >= record["expires_at"]:
            _sessions.pop(session_id, None)
            raise HTTPException(401, "Session expired. Please reconnect.")

        if record["owner"] != owner_id:
            raise HTTPException(401, "Wrong owner.")

        record["expires_at"] = now + settings.session_ttl
        return record["cache"]


def clear_app_session(request: Request, response: Response):
    session_id = request.cookies.get(settings.session_cookie)

    with _lock:
        if session_id:
            _sessions.pop(session_id, None)

    response.delete_cookie(
        settings.session_cookie,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
