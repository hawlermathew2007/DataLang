from pydantic import BaseModel
from typing import Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from governance.schemas.database import DatabaseCredentials


class Message(BaseModel):
    id: str
    owner_id: str
    message: str


@dataclass
class Cache:
    id: str
    owner_id: str
    holder: Union[Message, DatabaseCredentials]
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime = field(
        default_factory=lambda: (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        )
    )


# Replace this with Redis Cache in the future and sensitive need encryption
_messages: dict[str, Message] = {}
_caches: dict[str, Cache] = {}


def create_message(message: str):
    return Message(
        id=str(uuid4()),
        message=message,
    )


def create_cache(holder: dict, owner_id: str = "ABCUUID") -> Cache:
    cache = Cache(
        id=str(uuid4()),
        owner_id=owner_id,
        holder=holder,
    )
    _caches[cache.id] = cache
    return cache


def get_cache(cache_id: str) -> Cache | None:
    cache = _caches.get(cache_id)

    if cache is None:
        return None

    if datetime.now(timezone.utc) >= cache.expires_at:
        _caches.pop(cache_id, None)
        return None

    return cache
