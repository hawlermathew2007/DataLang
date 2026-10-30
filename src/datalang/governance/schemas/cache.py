import uuid
from pydantic import BaseModel, Field
from typing import Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from governance.schemas.database import DatabaseCredentials


class Message(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_id: str
    message: str


@dataclass
class Cache:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    owner_id: str = "ABCUUID"
    holder: Union[Message, DatabaseCredentials, None] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime = field(
        default_factory=lambda: (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        )
    )


# Replace this with Redis Cache in the future and sensitive need encryption
_messages: dict[uuid.UUID, Message] = {}
_caches: dict[uuid.UUID, Cache] = {}


def create_message(message: str):
    return Message(
        message=message,
    )


def create_cache(holder: dict, owner_id: str = "ABCUUID") -> Cache:
    cache = Cache(
        owner_id=owner_id,
        holder=holder,
    )
    _caches[cache.id] = cache
    return cache
