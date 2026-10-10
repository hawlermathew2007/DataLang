import psycopg2
from .conn import get_db_connection


CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS test_users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(254) UNIQUE,
    disabled BOOLEAN NOT NULL DEFAULT FALSE,
    role INTEGER NOT NULL DEFAULT 1
        CHECK (role IN (0, 1, 2)),
    hashed_password TEXT NOT NULL
);
"""


def setup_database():
    conn = None

    try:
        conn = get_db_connection()

        with conn:
            with conn.cursor() as cursor:
                cursor.execute(CREATE_USERS_TABLE)

        print("Database setup successful: test_users table is ready.")

    except (psycopg2.Error, KeyError) as exc:
        print(f"Database setup failed: {exc}")
        raise

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    print("Start setting up Yugabye DB...")
    setup_database()
    print("[*] Done :)")
