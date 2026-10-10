from pydantic import BaseModel
from backend.shared.role import Role


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
    role: Role
