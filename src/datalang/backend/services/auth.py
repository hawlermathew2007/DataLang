from backend.databases.conn import get_db_connection
from backend.utils.password import verify_password
from backend.utils.user import get_user


def authenticate_user(
            username: str,
            password: str,
        ):

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT hashed_password
                FROM test_users
                WHERE username = %s
                """,
                (username,),
            )
            row = cursor.fetchone()

        if not row:
            return False

        db_hash = row["hashed_password"]

        if not verify_password(password, db_hash):
            return False

        return get_user(username)

    finally:
        conn.close()
