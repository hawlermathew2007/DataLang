from fastapi import APIRouter, Depends
from typing import Annotated

from backend.schemas.user import UserCred
from backend.utils.user import get_current_active_user

user_router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@user_router.get("/me/")
async def read_users_me(
    current_user: Annotated[UserCred, Depends(get_current_active_user)],
) -> UserCred:
    return current_user
