from pydantic import BaseModel, EmailStr
from backend.shared.role import Role
import uuid


class User(BaseModel):
    id: uuid.UUID  # uuid.uuid4()
    username: str
    email: EmailStr | None = None
    disabled: bool | None = None
    role: Role


class UserCred(User):
    hashed_password: str
