"""Set up DB: Create a new table for data auth"""
import psycopg2
from psycopg2.extras import RealDictCursor
from collections.abc import Generator

from backend.core.config import DB_INFO


def get_db_connection():
    return psycopg2.connect(
        host=DB_INFO["host"],
        port=DB_INFO["port"],
        dbname=DB_INFO["dbName"],
        user=DB_INFO["dbUser"],
        password=DB_INFO["dbPassword"],
        cursor_factory=RealDictCursor,
    )


def get_db() -> Generator:
    conn = get_db_connection()

    try:
        yield conn
    finally:
        conn.close()
