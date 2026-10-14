from pydantic import BaseModel, EmailStr, Field
from backend.shared.role import Role


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=12, max_length=128)
    email: EmailStr | None = None
    role: Role = Role.Visitor
