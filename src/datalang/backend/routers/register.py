import uuid

import psycopg2
from fastapi import APIRouter, HTTPException, status
from pwdlib import PasswordHash

from backend.databases.conn import get_db_connection
from backend.schemas.auth import RegisterRequest
from backend.schemas.user import User

register_router = APIRouter(
    prefix="/register",
    tags=["Register"],
)

password_hash = PasswordHash.recommended()


@register_router.post(
    "/",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: RegisterRequest):
    user_id = uuid.uuid4()

    # Hash the password on the server.
    hashed_password = password_hash.hash(payload.password)

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO test_users (
                    id,
                    username,
                    email,
                    disabled,
                    role,
                    hashed_password
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, username, email, disabled, role
                """,
                (
                    str(user_id),
                    payload.username,
                    str(payload.email) if payload.email else None,
                    False,
                    1,  # Role.Visitor
                    hashed_password,
                ),
            )
            created_user = cursor.fetchone()

        conn.commit()
        return User(**created_user)

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        )

    finally:
        conn.close()
