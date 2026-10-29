import psycopg2
import jwt
import logging
from jwt.exceptions import InvalidTokenError
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.core.config import SECRET_KEY, ALGORITHM
from backend.schemas.token import TokenData
from backend.schemas.user import User, UserCred
from backend.shared.role import Role
from backend.databases.conn import get_db_connection

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/token")
logging.basicConfig(
    filename='app.log',
    filemode='w',  # 'w' overwrites the file; 'a' appends (default)
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_user(
        username: str) -> User | None:

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, email, disabled, role, hashed_password
                FROM test_users
                WHERE username = %s
                """,
                (username,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return UserCred(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                disabled=row["disabled"],
                role=Role(row["role"]),
                hashed_password=row["hashed_password"],
            )

    except psycopg2.Error as e:
        conn.rollback()
        print(f"get_user failed: {e}")
        raise

    finally:
        conn.close()


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)

    except InvalidTokenError as e:
        logging.exception("JWT decode failed: %r", e)
        raise credentials_exception

    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[UserCred, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user
